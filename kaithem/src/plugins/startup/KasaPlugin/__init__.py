#Plugin that manages TP-Link Kasa devices.

from src import devices,alerts, scheduling,tagpoints,messagebus
import os,mako,time,threading,logging

try:
	from pyHS100 import SmartPlug, SmartBulb
except:
	logger.exception()
	messagebus.postMessage("/system/notifications/errors","Problem loading Kasa support")

from src import widgets

logger = logging.Logger("plugins.kasa")

from mako.lookup import TemplateLookup
templateGetter = TemplateLookup(os.path.dirname(__file__))


lookup={}

lastRefreshed = 0

lock = threading.Lock()

def maybeRefresh(t=30):
	global lastRefreshed
	if lastRefreshed<time.time()-t:
		refresh()
	elif lastRefreshed<time.time()-5:
		refresh(1)

def refresh(timeout=8):
	global lastRefreshed,lookup
	from pyHS100 import Discover
	lastRefreshed= time.time()
	allDevices=  Discover.discover(timeout=timeout)
	l={}

	#Build a structure that allows lookup by both type and IP address
	for i in allDevices:
		try:
			l[allDevices[i].alias] = allDevices[i]
		except:
			logger.exception()
	lookup=l



def isIp(x):
	x=x.strip().split('.')
	try:
		x = [int(i) for i in x]
		if len(x)==4:
			return True
	except:
		return False
	
def getDevice(locator,timeout=10,klass=None):
	"""Since plugs can change name, you should't keep a reference
	to a plug for too long. Instead use this function.
	"""
	global lookup
	if not isIp(locator):
		if locator in lookup:
			return lookup[locator]
		
		maybeRefresh()
		if locator in lookup:
			return lookup[locator]
		
	return klass(locator)


class KasaDevice(devices.Device):
	def __init__(self,name,data):
		self.lock = threading.Lock()
		self.rssiCache =0
		self.rssiCacheTime = 0
		#We really don't need either of these to have persistent alerts.
		self.lowSignalAlert = alerts.Alert(name+".lowsignalalert",tripDelay=80,autoAck=True)
		self.unreachableAlert = alerts.Alert(name+".unreachablealert", autoAck=True)
		self.lastLoggedUnreachable = 0
		devices.Device.__init__(self,name,data)

		try:

			if not data.get("device.locator",''):
				self.setDataKey("device.locator",data.get('temp.locator',''))
			
			#If we were given separate temp and permanent names, then we use the temp
			#To find the device and set it to the proper permanent name
			if not data['device.locator']==data.get('temp.locator',data['device.locator']):
				getDevice(data['temp.locator'],5,self.kdClass).alias = data['device.locator']
				refresh()


			#Allow changing WiFi
			if data.get('temp.ssid',''):
				getDevice(data['device.locator'],10,self.kdClass).set_wifi(data.get('temp.ssid'), data.get('temp.psk'))

		except:
			self.handleError()
			
	def getRawDevice(self):
		return getDevice(self.data.get("device.locator"),3,self.kdClass)

	def rssi(self,cacheFor=120):
		with self.lock:
			"Returns the current RSSI value of the device"
			if time.time()-self.rssiCacheTime<cacheFor:
				return self.rssiCache

			#Not ideal, but we really can't be retrying this too often.
			#if it's disconnected. Way too much slowdown
			self.rssiCacheTime=time.time()

			try:
				info = getDevice(self.data.get("device.locator"),3,self.kdClass).get_sysinfo()
				self.rssiCache= info['rssi']
				#It's just a handy place to get this info because
				#we're getting sysinfo anyway.
				self._has_emeter = ('model' in info) and ('HS110' in info['model'])
			except:
				if self.lastLoggedUnreachable< time.monotonic()-30:
					self.handleError("Device was unreachable")
					self.lastLoggedUnreachable=time.monotonic()
				self.unreachableAlert.trip()
				raise

			#Obviously not unreachable if we just got the RSSI!
			self.unreachableAlert.clear()

			if self.rssiCache>-85:
				self.lowSignalAlert.clear()
			if self.rssiCache<-89:
				self.lowSignalAlert.trip()

			return self.rssiCache

	@staticmethod
	def getCreateForm():
		return templateGetter.get_template("createform.html").render()
	
class KasaSmartplug(KasaDevice):
	deviceTypeName="KasaSmartplug"
	kdClass = SmartPlug
	descriptors={
		"kaithem.device.powerswitch":1,
		"kaithem.device.rssi":-80
	}

	def __init__(self,name,data):
		KasaDevice.__init__(self,name,data)

		#Assume no e-meter till we're told otherwise
		self._has_emeter = False

		self.analogChannels=[["W"]]


		self.highCurrentAlert = alerts.Alert(priority='warning', name=name+".highcurrentalert", autoAck=False)
		self.overCurrentAlert = alerts.Alert(priority='error', name=name+".overcurrentalert", autoAck=False)

		#Set it up with a tagpoint
		self.switchTagPoint = tagpoints.Tag("/devices/"+self.name+".switch")
		self.switchTagPoint.min=0
		self.switchTagPoint.max=1
		self.switchTagPoint.owner= "Kasa Smartplug"



		self.tagPoints={
			"switch": self.switchTagPoint
		}

		def switchTagHandler(v,ts, a):
			try:
				self.setSwitch(0,v>=0.5)
			except:
				pass

		def switchTagGetter():
			try:
				return 1 if self.getSwitch(0) else 0
			except:
				return None
		self.switchTagPoint.claim(switchTagGetter)

		self.sth = switchTagHandler

		#We use the handler to set this. This means that an error will
		#Be raised if we try to set the tag with an unreachable device
		self.switchTagPoint.setHandler(switchTagHandler)

		#We probably don't need to poll this too often
		self.switchTagPoint.interval= 3600

		self.tagPoints={
			"switch":self.switchTagPoint
		}

		self.alerts={
			"unreachableAlert":self.unreachableAlert,
			"lowSignalAlert": self.lowSignalAlert,
			'highCurrentAlert':self.highCurrentAlert,
			'overCurrentAlert':self.overCurrentAlert
		}

	

	
		self.setAlertPriorities()
		try:
			#Check RSSI as soon as we create the obj to trigger any alerts based on it.
			self.rssi()
		except:
			pass
		
		self.s = scheduling.scheduler.everyMinute(self._pollRssi)

		def onf(user,value):
			if 'pushed' in value:
				self.setSwitch(0,True)
		def offf(user,value):
			if 'pushed' in value:
				self.setSwitch(0,False)
		
		self.onButton = widgets.Button()
		self.offButton=widgets.Button()
		self.onButton.attach(onf)
		self.offButton.attach(offf)

		self.powerWidget = widgets.Meter(high_warn=float(data.get("alarmcurrent",1400)), max=1600,min=0)

	def getManagementForm(self):
		try:
			self.rssi(2)
		except:
			pass
		return templateGetter.get_template("manageform.html").render(data=self.data,obj=self)

	def setSwitch(self,channel, state):
		logger.debug("Setting smartplug "+self.data.get("device.locator")+ "to state "+str(state))
		with self.lock:
			"Set the state of switch channel N"
			if channel>0:
				raise ValueError("This is a 1 channel device")
			try:
				if state:
					if not self.overCurrentAlert.sm.state=="normal":
						raise RuntimeError("You cannot turn the switch on while the overcurrent shutdown has an unacknowledged error")
					getDevice(self.data.get("device.locator"),3,self.kdClass).turn_on()
				else:
					getDevice(self.data.get("device.locator"),3, self.kdClass).turn_off()
			except:
				if self.lastLoggedUnreachable< time.monotonic()-30:
					self.handleError("Device was unreachable")
					self.lastLoggedUnreachable=time.monotonic()
				self.unreachableAlert.trip()
				raise

			#Obviously not unreachable if we just got the RSSI!
			self.unreachableAlert.clear()

	def getSwitch(self,channel):
		with self.lock:
			"Set the state of switch channel N"
			if channel>0:
				raise ValueError("This is a 1 channel device")
			try:
				s = getDevice(self.data.get("device.locator"),3,self.kdClass).state=="ON"
			except:
				if self.lastLoggedUnreachable< time.monotonic()-30:
					self.handleError("Device was unreachable")
					self.lastLoggedUnreachable=time.monotonic()
				self.unreachableAlert.trip()
				raise

			#Obviously not unreachable if we just got the RSSI!
			self.unreachableAlert.clear()
			return s
		
	
	def getEnergyStats(self,channel):
		if channel>0:
			raise ValueError("This is a 1 channel device")
		try:
			s = getDevice(self.data.get("device.locator"),3, self.kdClass).get_emeter_realtime()
			self.doOvercurrentHandling(s)
		except:
			#Try to get RSSI to test if it works at all and set the alert as needed.
			try:
				self.rssi()
			except:
				pass
			raise
		#Obviously not unreachable if we just got the RSSI!
		self.unreachableAlert.clear()
		return s

	def _pollRssi(self):
		"Background polling of RSSI to detect when things are available or not"
		
		#No reason to poll if we already know we can't reach it.
		if not self.data.get('device.locator',None):
			return
		try:
			self.rssi(cacheFor=10)
			#Also do this here as well
			self._pollEnergy()
		except:
			pass

	def _pollEnergy(self):
		"Background polling of RSSI to detect when things are available or not"        
		#No reason to poll if we already know we can't reach it.
		if not self.data.get('device.locator',None):
			return
		#Don't bother if we don't have the meter anyway
		if not self._has_emeter:
			return
		try:
			self.getEnergyStats(0)
		except:
			logging.exception("Err")

	def doOvercurrentHandling(self,x):
		w= x['current']*x['voltage']
		self.powerWidget.write(w)

		limit = float(self.data.get("device.alarmcurrent", 1500))
		hardlimit =float(self.data.get("device.maxcurrent", 1600))

		if w> limit:
			self.highCurrentAlert.trip()
		else:
			self.highCurrentAlert.clear()
			self.overCurrentAlert.clear()

		#Note: does nothing about multiple channels.
		if w>hardlimit:
			self.setSwitch(0, False)
			self.overCurrentAlert.trip()




class KasaBulb(KasaDevice):
	deviceTypeName="KasaSmartbulb"
	kdClass = SmartBulb
	descriptors={
		"kaithem.device.hsv": 1,
		"kaithem.device.powerswitch":1,
		"kaithem.device.rssi":-80
	}

	def __init__(self,name,data):
		KasaDevice.__init__(self,name,data)
		self.lastHueChange = time.monotonic()

		#Set it up with a tagpoint
		self.switchTagPoint = tagpoints.Tag("/devices/"+self.name+".switch")
		self.switchTagPoint.min=0
		self.switchTagPoint.max=1
		self.switchTagPoint.owner= "Kasa Smartplug"



		self.tagPoints={
			"switch": self.switchTagPoint
		}

		def switchTagHandler(v,ts, a):
			try:
				self.setSwitch(0,v>=0.5)
			except:
				pass

		def switchTagGetter():
			try:
				return 1 if self.getSwitch(0) else 0
			except:
				return None
		self.switchTagPoint.claim(switchTagGetter)

		self.sth = switchTagHandler

		#We use the handler to set this. This means that an error will
		#Be raised if we try to set the tag with an unreachable device
		self.switchTagPoint.setHandler(switchTagHandler)

		#We probably don't need to poll this too often
		self.switchTagPoint.interval= 3600

		self.tagPoints={
			"switch":self.switchTagPoint
		}
		def onf(user,value):
			if 'pushed' in value:
				self.setSwitch(0,True)

		def offf(user,value):
			if 'pushed' in value:
				self.setSwitch(0,False)

		def hsvf(user,value):
			if time.monotonic()-self.lastHueChange>1:
				self.setHSV(0,self.hwidget.value,self.swidget.value,self.vwidget.value)
				self.lastHueChange=time.monotonic()

		self.hwidget = widgets.Slider(max=360)
		self.swidget = widgets.Slider(max=1,step=0.01)
		self.vwidget = widgets.Slider(max=1,step=0.01)
		self.csetButton = widgets.Button()

		self.csetButton.attach(hsvf)
	


		self.onButton = widgets.Button()

		self.offButton=widgets.Button()
		self.onButton.attach(onf)
		self.offButton.attach(offf)
		self.huesat =-1
		self.lastVal =-1
		self.wasOff=True
		self.oldTransitionRate = -1

	def getSwitch(self,channel, state):
		if channel>0:
			raise ValueError("Bulb has 1 master power channel only")
		return  self.getRawDevice().is_on




	def setSwitch(self,channel, state,duration=1):
		logger.debug("Setting smartplug "+self.data.get("device.locator")+ "to state "+str(state))
		with self.lock:
			"Set the state of switch channel N"
			if channel>0:
				raise ValueError("This is a 1 channel device")
			try:
				if state:
					getDevice(self.data.get("device.locator"),3,self.kdClass).turn_on(duration)
					self.wasOff=False
				else:
					getDevice(self.data.get("device.locator"),3,self.kdClass).turn_off(duration)
					self.wasOff=True
				self.oldTransitionRate=duration
			except:
				if self.lastLoggedUnreachable< time.monotonic()-30:
					self.handleError("Device was unreachable")
					self.lastLoggedUnreachable=time.monotonic()
				self.unreachableAlert.trip()
				raise

			#Obviously not unreachable
			self.unreachableAlert.clear()
	
	def setHSV(self,channel, hue,sat,val,duration=1):
		if channel>0:
			raise ValueError("Bulb has 1 color only")

		#The idea here is that if the color has not changed, 
		#We can issue a direct on/off command instead, which is both more semantic,
		#And in theory less damaging to flash memory if they did it right.
		huesat = (int(hue),int(sat*100))

		if huesat == self.huesat or val < 0.01 or (val==self.lastVal):
			if val < 0.01:
				self.wasOff = True
				self.setSwitch(0,False,duration)
			else:
				if self.wasOff and (huesat == self.huesat) and (val==self.lastVal):
					self.setSwitch(0,True,duration)
				else:
					self.getRawDevice().set_hsv((int(hue),int(sat*100),int(val*100)),duration)
					self.lastVal=val
					self.huesat = huesat
				self.wasOff=False

		else:
			self.getRawDevice().set_hsv((int(hue),int(sat*100),int(val*100)),duration if not self.wasOff else 0)
			if self.wasOff:
				self.wasOff=False
				self.setSwitch(0,True,duration)
			self.huesat = huesat
			self.lastVal = val

	@staticmethod
	def getCreateForm():
		return templateGetter.get_template("createform.html").render()

	def getManagementForm(self):
		return templateGetter.get_template("bulbpage.html").render(data=self.data,obj=self)

devices.deviceTypes["KasaSmartplug"]=KasaSmartplug
devices.deviceTypes["KasaSmartbulb"]=KasaBulb
