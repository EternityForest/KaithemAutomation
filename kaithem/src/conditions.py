#This module manages coditions whitch



class Condition():
	def __init__(self,name,level ='info',description = None):
		if description==None:
			self.description = "Condition " + name + " is active."
		else:
			self.description = description
		
		self.name = name
		self.level = 'info'

class Conditions():
	def __init__(self):
		self.conditions = {}
		self.levelstonumbers = {'info':1,'warning':2,'fault':3}
	##Open a new codition, i.e. tell the system the codition applies
	def open(self,name,level = 'info',description):
		self.conditions[name] = Condition(name,level,description)
	
	##Delete a condition, i.e. tell the system it no longer applies
	def close(self,name):
		del self.conditions[name]
		
	def getConditions(self,level):
	