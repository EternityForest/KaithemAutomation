import collections
import configparser
from hardline import daemonconfig
from .. import daemonconfig, hardline


import configparser,logging,textwrap,uuid

from kivy.uix.image import Image
from kivy.uix.widget import Widget

from typing import Sized, Text
from kivy.utils import platform
from kivymd.uix.button import MDFillRoundFlatButton as Button, MDRoundFlatButton
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextFieldRect,MDTextField
from kivymd.uix.label import MDLabel as Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivymd.uix.toolbar import MDToolbar
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout as BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen

import time
import traceback

# Terrible Hacc, because otherwise we cannot iumport hardline on android.
import os
import sys
import re
import random
from .. daemonconfig import makeUserDatabase
from .. import drayerdb, cidict

from kivymd.uix.picker import MDDatePicker

import functools

#Regex used to spot FORM expressions 
forms_regex = r'''FORM *\( *['"](.*?)['"] *\)'''

def cacheWrap(f):
    w = functools.lru_cache(maxsize=128, typed=False)
    f = w(f)

    def f2(*a):
        if not hasattr(f, 'cacheClearTime') or  (cacheClearTime[0] > f.cacheClearTime) or (cacheClearTime[0]<time.time()-1200):
            f.cache_clear()
            f.cacheClearTime = cacheClearTime[0]
        return f(*a)
    return f2



def makePostRenderingFuncs(limit=1024*1024):
    @cacheWrap
    def spreadsheetSum(p):
        t=0
        n=0
        for i in p:
            try:
                i=float(i)
                n+=1
            except:
                continue
            if n>limit:
                return float('nan')
            t+=i
        return t

    def spreadsheetConvert(p, unit, to):
        import pint
        return pint.Quantity(float(p),unit).to(to).magnitude
    
    @cacheWrap
    def spreadsheetLatest(p):
        for i in p:
            return t

    @cacheWrap
    def spreadsheetRandSelect(p):
        l = []
        v=limit
        for i in p:
            v-=1
            if v<0:
                break
            l.append(i)
        return random.choice(l)

    @cacheWrap
    def spreadsheetAvg(p):
        t=0
        n =0
        for i in p:
            try:
                i=float(i)
                n+=1
            except:
                continue

            if n>limit:
                return float('nan')
            t+=i
        return t/n
    
    funcs = {'SUM':spreadsheetSum, 'AVG':spreadsheetAvg,'LATEST':spreadsheetLatest,'RANDSELECT':spreadsheetRandSelect, 'CONVERT':spreadsheetConvert}
    return funcs

prf_full = makePostRenderingFuncs()
prf_limit = makePostRenderingFuncs(8193)

def getPostRenderingFunctions(limit):
    if limit:
        return prf_limit
    else:
        return prf_full

class ColumnIterator():
    def __init__(self, db,postPath, col):
        self._col = col
        self._db = db
        self._postPath= postPath

    def __iter__(self):
        self._cur = self._db.getDocumentsByType("row", parent=self._postPath, limit=10240000000,allowOrphans=True)
        return self

    def __next__(self):
        for i in self._cur:
            if self._col in i:
                return i[self._col]
        raise StopIteration

    def __hash__(self):
        return hash((self._col, self._db.filename))

    def __eq__(self, other):
        return (self._col, self._db.filename) == (self._col, self._db.filename)


def renderPostTemplate(db, postID,text, limit=100000000):
    "Render any {{expressions}} in a post based on that post's child data row objects.  Currentlt limit is rounded to just above or below 8192"


    if hasattr(db,'enableSpreadsheetEval'):
        esf=db.enableSpreadsheetEval
    else:
        esf=True

    if not esf:
        return text
            

    search=list(re.finditer(r'\{\{(.*?)\}\}',text))
    if not search:
        return text
    
    d = db.getDocumentByID(postID,allowOrphans=True)
    if not d:
        return ''

    #Need to be able to go slightly 
    rows = db.getDocumentsByType('row',parent=postID,allowOrphans=True)

    ctx = {}
    
    n = 0
    for i in rows:
        n+=1
        if n>limit:
            return text
        for j in i:
            if j.startswith("row."):
                ctx[j[4:]]=ColumnIterator(db,postID, j)
                
    replacements ={}
    for i in search:
        if not i.group() in replacements:
            try:
                from ..simpleeval import simple_eval
                from .. import simpleeval
                simpleeval.POWER_MAX = 512
                replacements[i.group()] = simple_eval(i.group(1), names= ctx, functions=getPostRenderingFunctions(limit>8193))
            except Exception as e:
                logging.exception("Error in template expression in a post")
                replacements[i.group()] = e
    
    for i in replacements:
        text = text.replace(i, str(replacements[i]))
    
    return text

cacheClearTime=[time.time()]
class TablesMixin():

    def clearSpreadsheetCache(self):
        cacheClearTime[0]=time.time()

    def gotoTableView(self, stream, parent='', search=''):
        "Data records can be attatched to a post."
        self.currentPageNewRecordHandler=None
        self.streamEditPanel.clear_widgets()
        s = daemonconfig.userDatabases[stream]
        parentDoc=daemonconfig.userDatabases[stream].getDocumentByID(parent,allowOrphans=True)
        self.streamEditPanel.add_widget(self.makeBackButton())

        postWidget=self.makePostWidget(stream,parentDoc,indexAssumption=False)
        self.streamEditPanel.add_widget(postWidget)
        self.streamEditPanel.add_widget((MDToolbar(title="Data Table View")))
            

        topbar = BoxLayout(orientation="horizontal",spacing=10,adaptive_height=True)

        searchBar = BoxLayout(orientation="horizontal",spacing=10,adaptive_height=True)

        searchQuery = MDTextField(size_hint=(0.68,None),multiline=False, text=search)
        searchButton = MDRoundFlatButton(text="Search")
        searchBar.add_widget(searchQuery)
        searchBar.add_widget(searchButton)

        def doSearch(*a):
            self.currentPageNewRecordHandler=None
            self.gotoTableView(stream, parent,searchQuery.text.strip())
        searchButton.bind(on_release=doSearch)

        def goHere():
            self.currentPageNewRecordHandler=None
            self.gotoTableView( stream, parent,search)
        self.backStack.append(goHere)
        self.backStack = self.backStack[-50:]

        newEntryBar = BoxLayout(orientation="horizontal",spacing=10,adaptive_height=True)


        newRowName = MDTextField(size_hint=(0.68,None),multiline=False, text=search)
        def write(*a):
            for i in  newRowName.text:
                if i in "[]{}:,./\\":
                    return

            if newRowName.text.strip():
                id = uuid.uuid5(uuid.UUID(parent),newRowName.text.strip().lower().replace(' ',""))
                #That name already exists, jump to it
                if daemonconfig.userDatabases[stream].getDocumentByID(id,allowOrphans=True):
                    self.currentPageNewRecordHandler=None
                    self.gotoStreamRow(stream, id)
                    return
            else:
                id=str(uuid.uuid4())
            
            x = daemonconfig.userDatabases[stream].getDocumentsByType("row.template", parent=parent,limit=1,allowOrphans=True) 
            newDoc = {'parent': parent,'id':id, 'name':newRowName.text.strip() or id, 'type':'row', 'leafNode':True}

            #Use the previously created or modified row as the template
            for i in x:
                for j in i:
                    if j.startswith('row.'):
                        newDoc[j]= ''

            self.currentPageNewRecordHandler=None
            self.gotoStreamRow(stream, id, newDoc)

        btn1 = Button(text='New Entry')

        btn1.bind(on_press=write)
        newEntryBar.add_widget(newRowName)
        newEntryBar.add_widget(btn1)

        if s.writePassword:
            topbar.add_widget(newEntryBar)

        self.streamEditPanel.add_widget(topbar)
        
        if not search:
            p = s.getDocumentsByType("row", limit=1000, parent=parent,allowOrphans=True)
        else:
            p = s.searchDocuments(search,"row", limit=1000, parent=parent)



     

        self.streamEditPanel.add_widget(MDToolbar(title="Data Rows"))
        self.streamEditPanel.add_widget(searchBar)


       
        for i in p:
            self.streamEditPanel.add_widget(self.makeRowWidget(stream,i))
        self.screenManager.current = "EditStream"

        def onNewRecord(db,r,sig):
            if db is daemonconfig.userDatabases[stream]:
                if r.get('parent','')==parentDoc.get('parent','') and r['type']=="post":
                    if not self.unsavedDataCallback:
                        self.gotoStreamPost(stream,postID,noBack=True)

 
                elif parentDoc['id'] in r.get("parent",''):
                    postWidget.body.text = renderPostTemplate(daemonconfig.userDatabases[stream],parentDoc['id'], parentDoc.get("body",''))

  

        self.currentPageNewRecordHandler = onNewRecord




    
    def makeRowWidget(self,stream, post):
        def f(*a):
            self.currentPageNewRecordHandler=None
            self.gotoStreamRow(stream,post['id'])

        l = BoxLayout(adaptive_height=True,orientation='vertical')
        l.add_widget(Button(text=post.get('name',"?????"), on_release=f))
        
        tlen =0
        t = []
        for i in post:
            if i.startswith('row.') and not post[i] in (0,''):
                x = i[4:]+": "+str(post[i])[:16]+("..." if len(str(post[i]))>16 else "")
                if tlen+len(x)> 120:
                    continue
                t.append(x)
                tlen+=len(x)
        
        t ="\r\n".join(textwrap.wrap(",  ".join(t), 48))

        l.add_widget(self.saneLabel(t,l))
        return l

    def gotoStreamRow(self, stream, postID, document=None, noBack=False,template=None):
        "Editor/viewer for ONE specific row"
        self.streamEditPanel.clear_widgets()
        self.streamEditPanel.add_widget(MDToolbar(title="Table Row in "+stream))

        self.streamEditPanel.add_widget(self.makeBackButton())
        
        if not noBack:
            def goHere():
                self.gotoStreamRow(stream, postID)
            self.backStack.append(goHere)
            self.backStack = self.backStack[-50:]

        document = document or daemonconfig.userDatabases[stream].getDocumentByID(postID,allowOrphans=True)
        if 'type' in document and not document['type'] == 'row':
            raise RuntimeError("Document is not a row")
        document['type']='row'

        title = Label(text=document.get("name",''),font_size='22sp')

        #Our default template if none exists
        #Give it a name because eventually we may want to have multiple templates.
        #Give it an ID so it can override any existing children of that template.
        #Use only the direct ID of the parent record in cade we want to move it eventually.
        oldTemplate= {'type':"row.template",'leafNode':True, 'parent':document['parent'], 'name': 'default', 'id':uuid.uuid5(uuid.UUID(document['parent'].split("/")[-1]),".rowtemplate.default")}

        for i in daemonconfig.userDatabases[stream].getDocumentsByType("row.template", parent=document['parent'],limit=1,allowOrphans=True):
            oldTemplate=i

        template= template or oldTemplate


        def post(*a):
            with daemonconfig.userDatabases[stream]:
                #Make sure system knows this is not an old document
                try:
                    del document['time']
                except:
                    pass
                daemonconfig.userDatabases[stream].setDocument(document)

                #If the template has changed, that is how we know we need to save template changes at the same time as data changes
                if not template.get('time',0)==oldTemplate.get('time',1):
                    daemonconfig.userDatabases[stream].setDocument(template)
                daemonconfig.userDatabases[stream].commit()
                self.unsavedDataCallback=None

            self.goBack()
      
        btn1 = Button(text='Save Changes')
        btn1.bind(on_release=post)


        self.streamEditPanel.add_widget(title)
        
        buttons = BoxLayout(orientation="horizontal",spacing=10,adaptive_height=True)
              

        if daemonconfig.userDatabases[stream].writePassword:
            self.streamEditPanel.add_widget(buttons)  
            buttons.add_widget(btn1)



        def delete(*a):
            def reallyDelete(v):
                if v==postID:
                    with daemonconfig.userDatabases[stream]:
                        daemonconfig.userDatabases[stream].setDocument({'type':'null','id':postID})
                        daemonconfig.userDatabases[stream].commit()
                    self.gotoStreamPosts(stream)
            self.askQuestion("Delete table row permanently on all nodes?", postID, reallyDelete)

        btn1 = Button(text='Delete')
        btn1.bind(on_release=delete)

        if daemonconfig.userDatabases[stream].writePassword:
            buttons.add_widget(btn1)
            
        names ={}

        self.streamEditPanel.add_widget(MDToolbar(title="Data Columns:"))

        for i in template:
            if i.startswith('row.'):
                names[i]=''
               
        for i in document:
            if i.startswith('row.'):
                if i in template:
                    names[i]=''
                else:
                    #In the document but not the template, it is an old/obsolete column, show that to user.
                    names[i]='(removed)'
        
        for i in names:
            self.streamEditPanel.add_widget( Button( text=i[4:]))
            d = document.get(i,'')
            try:
                d=float(d)
            except:
                pass
                
            x = MDTextField(text=str(d)+names[i],mode='fill', multiline=False,font_size='22sp')
            def oc(*a,i=i,x=x):
                d=x.text.strip()
                if isinstance(d,str):
                    d=d.strip()
                try:
                    d=float(d or 0)
                except:
                    pass
                document[i]=d
            x.bind(text=oc)
            self.streamEditPanel.add_widget(x)

            if isinstance(d,float) or not d.strip():
                l = BoxLayout(orientation="horizontal",spacing=10,adaptive_height=True)
                b = MDRoundFlatButton(text="--")
                def f(*a, i=i, x=x):
                    d=document.get(i,'')
                    if isinstance(d,str):
                        d=d.strip()
                    try:
                        d=float(d or 0)
                    except:
                        return
                    document[i]=d-1
                    x.text=str(d-1)
                b.bind(on_release=f)

                b2 = MDRoundFlatButton(text="++")
                def f(*a, i=i, x=x):
                    d=document.get(i,'')
                    if isinstance(d,str):
                        d=d.strip()
                    try:
                        d=float(d or 0)
                    except:
                        return
                    document[i]=d+1
                    x.text=str(document[i])

                b2.bind(on_release=f)

                l.add_widget(b)
                l.add_widget(b2)
                self.streamEditPanel.add_widget(l)


        b = MDRoundFlatButton(text="Add Column")
        def f(*a):
            def f2(r):
                if r:
                    template['row.'+r]=''
                    #Remove time field which marks it as a new record that will get a new timestamp rather than
                    #being ignored when we go to save it, for being old.
                    template.pop('time',None)
                    #Redraw the whole page, it is lightweight, no DB operation needed.
                    self.gotoStreamRow(stream, postID, document=document, noBack=True,template=template)
            self.askQuestion("Name of new column?",cb=f2)

        b.bind(on_release=f)
        self.streamEditPanel.add_widget(b)

        b = MDRoundFlatButton(text="Del Column")
        def f(*a):
            def f2(r):
                if r:
                    try:
                       del template['row.'+r]
                       template.pop('time',None)
                    except:
                        pass
                    #Redraw the whole page, it is lightweight, no DB operation needed.
                    self.gotoStreamRow(stream, postID, document=document, noBack=True,template=template)
            self.askQuestion("Column to delete?",cb=f2)
                
        b.bind(on_release=f)
        self.streamEditPanel.add_widget(b)


        self.screenManager.current = "EditStream"