#!/usr/bin/env python

#TODO Sort it so it shows attempts as it runs through daofind without printing
#     out loads of lines (currently shows no progress)


import os
import subprocess
import threading
import atexit
import time

import tkFileDialog
from Tkinter import *

from pipemodules.functs import get_datetime

# the file and directory path to this script: in case you call it from 
# another directory, so relative paths to the script are still intact
FILEPATH = os.path.realpath(__file__)
FILEDIR = os.path.dirname(FILEPATH)

class OutputThread(threading.Thread):
    """
    Thread is called by the subprocess to output all text to gui without
    tying up the gui itself
    """
    def __init__(self,proc,master):
        threading.Thread.__init__(self)
        self.proc = proc
        self.master = master
    def run(self):
        while True:
            line = self.proc.stdout.readline()
            if line == '' and self.proc.poll() != None:
                break
            if line != '':
                print line.replace('\n', '') # stops all whitespace!


class SelfUpdateKillingButton(Button):
  """
  tkinter Button associated to a process to kill it.

  The button monitors the state of the process and is only active while
  the process is running. It sends a SIGTERM (subprocess.terminate) the
  first time it is activated, and a SIGKILL (subprocess.kill) any subsequent
  time. The Button can be re-used by other processes, simply update the value
  of self.proc.
  """
  def __init__(self, *args, **keywords):
    self.conf_running_not_killed_var = 0
    self.conf_running_killed_var = 1
    self.conf_not_running_var = 2
    self.conf = self.conf_not_running_var
    self.proc = keywords["proc"]
    self.rc = None
    self.killedOnce = False
    Button.__init__(self,command=self.kill_proc, state=DISABLED,
                    *args, **keywords) 
    self.auto_update()

  def kill_proc(self):
    if not self.killedOnce:
      print 'TERMINATE signal sent to pipe'
      self.killedOnce = True
      self.proc.terminate()
      self.conf_running_killed()
    else:
      print 'KILL signal sent to pipe'
      self.proc.kill()

  def conf_running_not_killed(self):
    self.conf = self.conf_running_not_killed_var
    self.configure(fg='black')
    self.configure(activeforeground='black')
    self.configure(text='STOP (term)')
    self.config(state=NORMAL)

  def conf_running_killed(self):
    self.conf = self.conf_running_killed_var
    self.configure(fg='red')
    self.configure(activeforeground='red')
    self.configure(text='STOP (kill)')
    self.config(state=NORMAL)

  def conf_not_running(self):
    self.killedOnce = False
    self.conf = self.conf_not_running_var
    self.config(state=DISABLED)
    self.configure(fg='black')
    self.configure(activeforeground='black')
    self.configure(text='kill')

  def auto_update(self):
    if self.proc is not None:
      self.rc = self.proc.poll()
    if self.rc is None:
      if self.killedOnce is not True:
        if self.conf != self.conf_running_killed_var:
          self.conf_running_not_killed()
      else:
        if self.conf != self.conf_running_killed_var:
          self.conf_running_killed()
    elif self.conf != self.conf_not_running_var:
      self.conf_not_running()


class Application(Frame):
    def __init__(self, master=None):
        self.master = master
        Frame.__init__(self,master)
        self.grid()

        self.pipechoice = StringVar()

        self.update = IntVar()
        self.fringe = IntVar()
        self.bpm = IntVar()

        self.tempclean = IntVar()

        self.imagecleaniter = IntVar()
        self.tempcleaniter = IntVar()

        self.reverse = IntVar()

        self.stamps = IntVar()

        self.subrundebug = IntVar()

        self.photrundebug = IntVar()

        self.clobber = IntVar()

        self.objcoo = IntVar()

        self.showresponse = IntVar()

        self.createWidgets()

        self.setdefaults(pipechoice="sub")
        

    def createWidgets(self):

        # Validate commands for various Entry boxes
        trimval = (self.register(self.trimValidate), 
                   '%d','%i','%P','%s','%S','%v','%V','%W')
        apval = (self.register(self.apValidate), 
                   '%d','%i','%P','%s','%S','%v','%V','%W')
        objcooval = (self.register(self.objcooValidate), 
                   '%d','%i','%P','%s','%S','%v','%V','%W')
        logval = (self.register(self.logValidate), 
                   '%d','%i','%P','%s','%S','%v','%V','%W')


        # CLASP logo
        self.clasplogo = Canvas(self,cursor="question_arrow",
                                height=125,width=200)
        self.clasplogo.pack(expand=YES, fill=BOTH)
        logo = PhotoImage(file=os.path.join(FILEDIR,"manual/CLASPsmall.gif"))
        self.clasplogo.create_image(0,0,image=logo,anchor=NW,tags="logo")
        self.clasplogo.photo = logo
        self.clasplogo.grid(row=0,columnspan=5)
        self.clasplogo.tag_bind("logo","<ButtonPress-1>",self.showmanual)
        clasplogo_tt = self.createToolTip(self.clasplogo,
                                   "Click to show the (in progress) manual")

        # Pipe choice
        self.subpipebutton = Radiobutton(self,text="Subtraction",
                                         variable=self.pipechoice,value="sub",
                                         command=self.switchpipe)
        self.subpipebutton.grid(row=1)
        self.photpipebutton = Radiobutton(self,text="Photometry",
                                          variable=self.pipechoice,
                                          value="phot",
                                          command=self.switchpipe)
        self.photpipebutton.grid(row=2)

        # Subtraction frame
        self.subframe = LabelFrame(self,text="Subtraction",padx=5,pady=5)
        self.subframe.grid(row=3)
        # Photometry frame
        self.photframe = LabelFrame(self,text="Photometry",padx=5,pady=5)
        self.photframe.grid(row=3)
        self.photframe.grid_remove()

        ############## Subtraction widgets ##############
        # Image path
        self.textlabel(self.subframe,"Image path*",0,0,E)
        self.imagepath = Entry(self.subframe,bg="white",width=50)
        self.imagepath.grid(row=0,column=1)
        # Image path file browser
        self.imagefilebrowser = Button(self.subframe,text="File",font=("Arial",7),width=2,
                            command=lambda e=1:self.filebrowser(self.imagepath))
        self.imagefilebrowser.grid(row=0,column=2,sticky=W)
        imagefilebroswer_tt = self.createToolTip(self.imagefilebrowser,"browse "
                              "for a single file to use as the input image")
        # Image path dir browser
        self.imagedirbrowser = Button(self.subframe,text="Dir",font=("Arial",7),width=2,
                            command=lambda e=1:self.dirbrowser(self.imagepath))
        self.imagedirbrowser.grid(row=0,column=2,sticky=E)
        imagedirbroswer_tt = self.createToolTip(self.imagedirbrowser,"browse "
                              "for a directory containing multiple images")
        # Selection
        self.textlabel(self.subframe,"Selection",1,0,E)
        self.selection = Entry(self.subframe,bg="white",width=17)
        self.selection.grid(row=1,column=1,sticky=W)
        selection_tt = self.createToolTip(self.selection,"the file pattern to "
                              "use if image path is a directory")
        # Template
        self.textlabel(self.subframe,"Template*",2,0,E)
        self.templatepath = Entry(self.subframe,bg="white",width=50)
        self.templatepath.grid(row=2,column=1)
        # Template browser
        self.templatebrowser = Button(self.subframe,text="Browse",
                            command=lambda e=1:self.filebrowser(self.templatepath))
        self.templatebrowser.grid(row=2,column=2)
        # Work dir
        self.textlabel(self.subframe,"Work directory*",3,0,E)
        self.subworkdir = Entry(self.subframe,bg="white",width=50)
        self.subworkdir.grid(row=3,column=1)
        subworkdir_tt = self.createToolTip(self.subworkdir,"a working directory"
                        " to store output files, created if non-existant")
        # Work dir browser
        self.workdirbrowser = Button(self.subframe,text="Browse",
                            command=lambda e=1:self.dirbrowser(self.subworkdir))
        self.workdirbrowser.grid(row=3,column=2)
        # Update
        self.textlabel(self.subframe,"Update previous work",4,0,E)
        self.updatebutton = Checkbutton(self.subframe,variable=self.update)
        self.updatebutton.grid(row=4,column=1,sticky=W)
        update_tt = self.createToolTip(self.updatebutton,"amend/add to an "
                                       "existing workdir")
        # Fringeframe
        self.textlabel(self.subframe,"Fringe frame",5,0,E)
        self.fringebutton = Checkbutton(self.subframe,
                                  variable=self.fringe,command=self.switchfringe)
        self.fringebutton.grid(row=5,column=1,sticky=W)
        self.fringepath = Entry(self.subframe,bg="white",width=45,state=DISABLED)
        self.fringepath.grid(row=5,column=1,sticky=E)
        # Fringeframe browser
        self.fringebrowser = Button(self.subframe,text="Browse",
                            command=lambda e=1:self.filebrowser(self.fringepath))
        self.fringebrowser.grid(row=5,column=2)
        # Badpixelmask
        self.textlabel(self.subframe,"Bad pixel mask",6,0,E)
        self.bpmbutton = Checkbutton(self.subframe,
                                  variable=self.bpm,command=self.switchbpm)
        self.bpmbutton.grid(row=6,column=1,sticky=W)
        self.bpmpath = Entry(self.subframe,bg="white",width=45,state=DISABLED)
        self.bpmpath.grid(row=6,column=1,sticky=E)
        # Badpixelmask browser
        self.bpmbrowser = Button(self.subframe,text="Browse",
                            command=lambda e=1:self.filebrowser(self.bpmpath))
        self.bpmbrowser.grid(row=6,column=2)
        # Clean template?
        self.textlabel(self.subframe,"Clean template",7,0,E)
        self.cleantempbutton = Checkbutton(self.subframe,variable=self.tempclean)
        self.cleantempbutton.grid(row=7,column=1,sticky=W)
        cleantemp_tt = self.createToolTip(self.cleantempbutton,"apply defringing"
                        " and bad pixel corrections to template as well as image(s)")
        # Cosmic ray iterations
        self.textlabel(self.subframe,"Cosmic ray iterations",8,0,E)
        self.cleanframe = Frame(self.subframe)
        self.cleanframe.grid(row=8,column=1)
        self.textlabel(self.cleanframe,"Image",0,0,W)
        for i in range(0,5):
            Radiobutton(self.cleanframe,text=i,variable=self.imagecleaniter,
                        value=i).grid(row=0,column=i+1,sticky=E)

        self.textlabel(self.cleanframe,"Template",1,0,W)
        for i in range(0,5):
            Radiobutton(self.cleanframe,text=i,variable=self.tempcleaniter,
                        value=i).grid(row=1,column=i+1,sticky=E)
        # Trim
        self.textlabel(self.subframe,"Trim",9,0,E)
        self.trim = Entry(self.subframe,bg="white",width=3,validate="key",
                          validatecommand=trimval)
        self.trim.grid(row=9,column=1,sticky=W)
        trim_tt = self.createToolTip(self.trim,"border (in pixels) to fix to "
                                "zero values around image edge")
        # Reverse
        self.textlabel(self.subframe,"Subtraction direction",10,0,E)
        self.reverseframe = Frame(self.subframe)
        self.reverseframe.grid(row=10,column=1)
        for i,txt in enumerate(["let program decide","reverse program decision",
                           "always convolve image","always convolve template"]):
            row = 0 if i<2 else 1
            column = 0 if i==0 or i==2 else 1
            Radiobutton(self.reverseframe,text=txt,variable=self.reverse,
                        value=i).grid(row=row,column=column,sticky=W)
        # Stamps
        self.textlabel(self.subframe,"Use own stamps",11,0,E)
        self.stampsbutton = Checkbutton(self.subframe,
                                  variable=self.stamps,command=self.switchstamps)
        self.stampsbutton.grid(row=11,column=1,sticky=W)
        self.stampspath = Entry(self.subframe,bg="white",width=45,state=DISABLED)
        self.stampspath.grid(row=11,column=1,sticky=E)
        # Stamps browser
        self.stampsbrowser = Button(self.subframe,text="Browse",
                            command=lambda e=1:self.filebrowser(self.stampspath,
                                    filetypes=[]))
        self.stampsbrowser.grid(row=11,column=2)
        # Run debug
        self.textlabel(self.subframe,"Output verbose/debug",12,0,E)
        self.updatebutton = Checkbutton(self.subframe,variable=self.subrundebug)
        self.updatebutton.grid(row=12,column=1,sticky=W)       

        ############## Photometry widgets ##############
        # Work dir
        self.textlabel(self.photframe,"Work directory*",0,0,E)
        self.photworkdir = Entry(self.photframe,bg="white",width=50)
        self.photworkdir.grid(row=0,column=1)
        photworkdir_tt = self.createToolTip(self.photworkdir,"The directory "\
                                            "containing output from Subtraction"\
                                            " pipeline.")
        # Work dir browser
        self.workdirbrowser = Button(self.photframe,text="Browse",
                            command=lambda e=1:self.dirbrowser(self.photworkdir))
        self.workdirbrowser.grid(row=0,column=2)
        # Clobber
        self.textlabel(self.photframe,"Clobber previous work",1,0,E)
        self.clobberbutton = Checkbutton(self.photframe,variable=self.clobber)
        self.clobberbutton.grid(row=1,column=1,sticky=W)
        clobber_tt = self.createToolTip(self.clobberbutton,"Overwrite previous"\
                                        " photometry files and lightcurve in "\
                                        " work directory")
        # Smallap
        self.textlabel(self.photframe,"Small aperture",2,0,E)
        self.smallap = Entry(self.photframe,bg="white",width=2,validate="key",
                          validatecommand=apval)
        self.smallap.grid(row=2,column=1,sticky=W)
        # Largeap
        self.textlabel(self.photframe,"Small aperture",3,0,E)
        self.largeap = Entry(self.photframe,bg="white",width=2,validate="key",
                          validatecommand=apval)
        self.largeap.grid(row=3,column=1,sticky=W)
        # Object coords
        self.textlabel(self.photframe,"Object coordinates",4,0,E)
        self.objcoobutton = Checkbutton(self.photframe,
                                  variable=self.objcoo,command=self.switchobjcoo)
        self.objcoobutton.grid(row=4,column=1,sticky=W)
        objcoobutton_tt = self.createToolTip(self.objcoobutton,"Use x and y "\
                          "pixel positions, if provided,\notherwise subtracted"\
                          " image is displayed\nto choose object coordinates")
        self.objcooframe = Frame(self.photframe)
        self.objcooframe.grid(row=4,column=1,padx=10)
        self.textlabel(self.objcooframe,"x:",0,0,W)
        self.objcoox = Entry(self.objcooframe,bg="white",width=8,validate="key",
                          validatecommand=objcooval,state=DISABLED)
        self.objcoox.grid(row=0,column=1,sticky=W)
        self.textlabel(self.objcooframe,"y:",0,2,W)
        self.objcooy = Entry(self.objcooframe,bg="white",width=8,validate="key",
                          validatecommand=objcooval,state=DISABLED)
        self.objcooy.grid(row=0,column=3,sticky=W)

        # Run debug
        self.textlabel(self.photframe,"Output verbose/debug",5,0,E)
        self.updatebutton = Checkbutton(self.photframe,variable=self.photrundebug)
        self.updatebutton.grid(row=5,column=1,sticky=W)
   
        # CLASP Command buttons
        self.cframe = Frame(self)
        self.cframe.grid(column=0)

        self.configframe = Frame(self.cframe)
        self.configframe.grid(row=0,columnspan=4)
        #self.textlabel(self.configframe,"Edit config files:",0,0,E)
        self.pipeconfigButton = Button(self.configframe,text="PIPE config",
                                       command=self.showpipeconfig)
        self.pipeconfigButton.grid(row=0,column=1)
        pipe_tt = self.createToolTip(self.pipeconfigButton,"Display the PIPE "
                                     "config file for editing")
        self.isisconfigButton = Button(self.configframe,text="ISIS config",
                                       command=self.showisisconfig)
        self.isisconfigButton.grid(row=0,column=2)
        pipe_tt = self.createToolTip(self.isisconfigButton,"Display the ISIS "
                                     "config file for editing")


        self.defaultsButton = Button(self.cframe, text='Set Defaults',
                                  command=self.setdefaults)
        self.defaultsButton.grid(row=1,column=1)

        #self.clroutputButton = Button(self.cframe, text='Clear Output',
        #                          command=self.clearoutput)
        #self.clroutpurButton.grid(row=1,column=1)
        #clroutput_tt = self.createToolTip(self.clroutputButton,
        #               ("Clear all output shown right")

        self.submitButton = Button(self.cframe,text="Start",command=self.submit,
                                   activebackground="green2")
        self.submitButton.grid(row=1,column=0)
        submit_tt = self.createToolTip(self.submitButton,"Start the selected "\
                                                         "pipe")

        # replacement for submit button, to kill pipe when running
        submitpos = self.submitButton.grid_info()
        self.killButton = SelfUpdateKillingButton(self.cframe,proc=None)
        kill_tt = self.createToolTip(self.killButton,"Terminate the currently"\
                                                     " running pipe")
        self.killButton.grid(submitpos)

        # quit button, needs to terminate pipe if it's running when pressed
        self.quitButton = Button(self.cframe,text='Quit',
                                 command=self.quit,activebackground="red")
        self.quitButton.grid(row=1,column=3)
        quit_tt = self.createToolTip(self.quitButton,"Exit CLASP")

        # A reponse Entry to handle stdin
        self.rframe = Frame(self)
        self.rframe.grid(column=0)


        self.textlabel(self.rframe,"response:",0,0)
        self.response = Entry(self.rframe,bg="white",width=60)
        self.response.grid(column=1,row=0,sticky=E)
        response_tt = self.createToolTip(self.response,"Enter input for pipes "\
                                         "in here, e.g. when asked y/n, "\
                                         "followed by Enter")


        # When user presses 'X' at top of window, check if we can kill the pipe
        # i.e. dont quit window while pipoe thread is alive.
        def myquit():
            for i in range(2):
                try:
                    self.killButton.kill_proc()
                except AttributeError:
                    break
                else:
                    pass
            self.quit()
        self.master.protocol("WM_DELETE_WINDOW",myquit)
                                         

    def setdefaults(self,pipechoice=None):
        if pipechoice:
            self.pipechoice.set(pipechoice)
        # Subtraction
        self.imagepath.delete(0,END)
        self.templatepath.delete(0,END)
        self.subworkdir.delete(0,END)
        self.selection.delete(0,END)
        self.selection.insert(0,"*.fits")
        self.fringe.set(0)
        self.fringepath.delete(0,END)
        self.fringepath.config(state=DISABLED)
        self.fringebrowser.config(state=DISABLED)
        self.bpm.set(0)
        self.bpmpath.delete(0,END)
        self.bpmpath.config(state=DISABLED)
        self.bpmbrowser.config(state=DISABLED)
        self.imagecleaniter.set(1)
        self.tempclean.set(0)
        self.tempcleaniter.set(1)
        self.trim.delete(0,END)
        self.trim.insert(0,5)
        self.reverse.set(0)
        self.stamps.set(0)
        self.stampspath.delete(0,END)
        self.stampspath.config(state=DISABLED)
        self.stampsbrowser.config(state=DISABLED)

        # Photometry
        self.photworkdir.delete(0,END)
        self.smallap.delete(0,END)
        self.smallap.insert(0,3)
        self.largeap.delete(0,END)
        self.largeap.insert(0,15)
        self.objcoo.set(0)
        self.objcoox.delete(0,END)
        self.objcoox.config(state=DISABLED)
        self.objcooy.delete(0,END)
        self.objcooy.config(state=DISABLED)

        # Other
        self.response.config(state=DISABLED)
        self.killButton.grid_remove()
        self.imagepath.insert(0,os.path.join(FILEDIR,"test","image.fits"))
        self.templatepath.insert(0,os.path.join(FILEDIR,"test","template.fits"))
        self.subworkdir.insert(0,os.path.join(FILEDIR,"test","testworkdir"))

    #def clroutput(self):
    #    pass#TODO


    def textlabel(self,parent,text,row,column,sticky=""):
        textlabel = Button(parent,text=text,disabledforeground="black",
                           fg="black",relief=FLAT,state=DISABLED)
        textlabel.grid(row=row,column=column,sticky=sticky)

    def showmanual(self,event):
        manualpath = os.path.join(FILEDIR,"manual","CLASP_readme.pdf")
        try:
            subprocess.Popen(("xdg-open",manualpath))
        except:
            print "Couldn't open %s" % manualpath

    def showpipeconfig(self):
        path = os.path.join(FILEDIR,"PIPEcfg.py")
        try:
            subprocess.Popen(("xdg-open",path))
        except:
            print "Couldn't open %s" % path

    def showisisconfig(self):
        path = os.path.join(FILEDIR,"ISIScfg.py")
        try:
            subprocess.Popen(("xdg-open",path))
        except:
            print "Couldn't open %s" % path

    def switchpipe(self):
        if self.pipechoice.get() == "sub":
            self.photframe.grid_remove()
            self.isisconfigButton.config(state=NORMAL)
            self.pipeconfigButton.config(state=NORMAL)
            self.subframe.grid()
        elif self.pipechoice.get() == "phot":
            self.subframe.grid_remove()
            # use subtraction workdir as a guess at phot workdir
            if not self.photworkdir.get():
                self.photworkdir.insert(0,self.subworkdir.get())
            self.isisconfigButton.config(state=DISABLED)
            self.pipeconfigButton.config(state=DISABLED)
            self.photframe.grid()

    def filebrowser(self,entry,filetypes=(("FITS", "*.fits"),("All files", "*.*"))):
        filename = tkFileDialog.askopenfilename(title="Choose a file",
                                filetypes = filetypes)
        if filename: 
            entry.delete(0,END)
            entry.insert(0,filename)
        return

    def dirbrowser(self,entry):
        filename = tkFileDialog.askdirectory(title="Choose a directory")
        if filename: 
            entry.delete(0,END)
            entry.insert(0,filename)
        return

    def switchfringe(self):
        if self.fringe.get():
            self.fringepath.config(state=NORMAL)
            self.fringebrowser.config(state=NORMAL)
        elif not self.fringe.get():
            self.fringepath.config(state=DISABLED)
            self.fringebrowser.config(state=DISABLED)

    def switchbpm(self):
        if self.bpm.get():
            self.bpmpath.config(state=NORMAL)
            self.bpmbrowser.config(state=NORMAL)
        elif not self.bpm.get():
            self.bpmpath.config(state=DISABLED)
            self.bpmbrowser.config(state=DISABLED)

    def switchobjcoo(self):
        if self.objcoo.get():
            self.objcoox.config(state=NORMAL)
            self.objcooy.config(state=NORMAL)
        elif not self.objcoo.get():
            self.objcoox.config(state=DISABLED)
            self.objcooy.config(state=DISABLED)


    def switchstamps(self):
        if self.stamps.get():
            self.stampspath.config(state=NORMAL)
            self.stampsbrowser.config(state=NORMAL)
        elif not self.stamps.get():
            self.stampspath.config(state=DISABLED)
            self.stampsbrowser.config(state=DISABLED)


    def trimValidate(self, d, i, P, s, S, v, V, W):
        # only allow integers <1000
        if int(i) > 2:
            return False
        try:
            int(S)
        except ValueError:
            return False
        else:
            return True

    def apValidate(self, d, i, P, s, S, v, V, W):
        # only allow integers <100
        if int(i) > 1:
            return False
        try:
            int(S)
        except ValueError:
            return False
        else:
            return True

    def objcooValidate(self, d, i, P, s, S, v, V, W):
        # only allow integers <100
        if int(i) > 5:
            return False
        if P:
            try:
                float(P)
            except ValueError:
                return False
            else:
                return True
        else:
            return True


    def logValidate(self, d, i, P, s, S, v, V, W):
        if S in ["/",","]:
            return False
        if not s and S == ".":
            return False
        return True
        

    def createToolTip(self,widget,text):
        toolTip = ToolTip(widget)
        def enter(event):
            toolTip.showtip(text)
        def leave(event): 
            toolTip.hidetip()
        widget.bind('<Enter>', enter)
        widget.bind('<Leave>', leave)


    def procmode(self,s=1):
        """
        convenience function to switch STATE of a load of buttons we don't
        want to be touch while a pipe is running and to reactivate them when
        it is finished/terminated
        s = 1: a pipe process is running
        s = 0: pipe process no longer running
        s != 1 and s !=0: ??? (something wrong!)
        """
        if s == 0:
            self.killButton.proc = None
            self.killButton.conf_not_running()
            self.killButton.grid_remove()
            self.submitButton.grid()
            self.response.delete(0,END)
            self.response.config(state=DISABLED)
            self.defaultsButton.config(state=NORMAL)
            self.subpipebutton.config(state=NORMAL)
            self.photpipebutton.config(state=NORMAL)
            self.quitButton.config(state=NORMAL)
        elif s == 1:
            self.submitButton.grid_remove()
            self.killButton.conf_running_not_killed()
            self.killButton.grid()
            self.response.config(state=NORMAL)
            self.defaultsButton.config(state=DISABLED)
            self.subpipebutton.config(state=DISABLED)
            self.photpipebutton.config(state=DISABLED)    
            self.quitButton.config(state=DISABLED)
        else:
            pass
            

    def submit(self):
        """
        Parse all options input by user and forward onto the appropriate pipe
        """
        print "="*79
        print get_datetime()
        print "INFO\tgenerating arguments for pipeline call..."
        def runpipe(argslist):
            """
            Call a subprocess with argslist (first entry should be script)
            Redirects sys.stdout to gui stdout and allows termination of 
            subprocess via 'killButton'
            """

            #self.switchresponse(1)
            print "INFO\tcalling {0} as:\n`{1}'".format(argslist[0],
                                                        " ".join(argslist))
            try:
                open(argslist[0])
            except IOError:
                print "ERROR\tcouldn't find {}".format(argslist[0])
                return
            else:
                pipeproc = subprocess.Popen(argslist,stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT,
                                            stdin=subprocess.PIPE)

            def responsereturn(event):
                pipeproc.stdin.write(self.response.get()+"\n")
                self.response.delete(0,END)
            self.response.bind("<Return>", responsereturn)
            self.response.bind("<KP_Enter>", responsereturn)

            # assign this process to the kill button to let the user terminate
            # /kill as necessary
            self.killButton.proc = pipeproc

            # thread the updating of the output so we don't tie up the gui
            thread1 = OutputThread(pipeproc,self)
            thread1.start()

            self.procmode(1)
            def checkprocrunning():
                if not thread1.is_alive():
                    self.procmode(0)
                    print "="*79+"\n"
                else:
                    self.after(150,checkprocrunning)
            checkprocrunning()

  
        if self.pipechoice.get() == "sub":
            for val in [self.imagepath,self.templatepath,self.subworkdir]:
                if not val.get():
                    print "ERROR\tensure all required (*) fields are filled!"
                    return
            # Now got support for stdin to subprocess. dont need prior checking
            #if os.path.isdir(self.subworkdir.get()):
            #    print "Subtraction work directory exists!"
            #    print "Remove it first, or choose another."
            #    return
            argslist = []
            argslist.extend([self.imagepath.get(),self.templatepath.get(),
                           self.subworkdir.get()])
            if self.selection.get():
                argslist.extend(["-s",self.selection.get()])
            if not self.selection.get():
                argslist.extend(["-s","*"])
            if self.update.get() == 1:
                argslist.append("-u")
            if self.fringe.get() == 1 and self.fringepath.get():
                argslist.extend(["-f",self.fringepath.get()])
            elif self.fringe.get() == 1 and not self.fringepath.get():
                print "WARNING\tno fringe frame file provided, skipping"
            if self.bpm.get() == 1 and self.bpmpath.get():
                argslist.extend(["-b",self.bpmpath.get()])
            elif self.bpm.get() == 1 and not self.bpmpath.get():
                print "WARNING\tno bad pixel mask file provided, skipping"
            if self.tempclean.get() == 1:
                argslist.append("-c")
            argslist.extend(["-ti",str(self.tempcleaniter.get())])
            argslist.extend(["-ii",str(self.imagecleaniter.get())])
            if self.trim.get():
                argslist.extend(["-t",str(self.trim.get())])
            argslist.extend(["-r",str(self.reverse.get())])
            if self.stamps.get() == 1 and self.stampspath.get():
                argslist.extend(["-stamps",self.stampspath.get()])
            elif self.stamps.get() == 1 and not self.stampspath.get():
                print "WARNING\tno stamps file provided, skipping"
            if self.subrundebug.get():
                argslist.append("-d")

            argslist.insert(0,os.path.join(FILEDIR,"run-subpipe.py"))



        if self.pipechoice.get() == "phot":
            if not self.photworkdir.get():
                    print "Ensure all required (*) fields are filled!"
                    return
            argslist = []
            argslist.append(self.photworkdir.get())

            if self.clobber.get():
                argslist.append("-c")
            if not self.smallap.get():
                argslist.extend(["-sa",3])
            else:
                argslist.extend(["-sa",self.smallap.get()])
            if not self.smallap.get():
                argslist.extend(["-la",15])
            else:
                argslist.extend(["-la",self.largeap.get()])
            if self.objcoo.get() == 1 and self.objcoox.get()\
                                            and self.objcooy.get():
                argslist.extend(["-o","{0},{1}".format(self.objcoox.get(),
                                                       self.objcooy.get())])
            if self.photrundebug.get():
                argslist.append("-d")
            argslist.insert(0,os.path.join(FILEDIR,"run-photpipe.py"))

        runpipe(argslist)
        # move keyboard focus to the response Entry widget
        self.response.focus_set()
                


class ToolTip(object):

    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text):
        self.text = text
        if self.tipwindow or not self.text: 
            return
        self.tipwindow = tw = Toplevel(self.widget)
        #x,y,cx,cy = self.widget.bbox("insert")
        x,y,cx,cy = 0,0,0,0
        x = x + self.widget.winfo_rootx() + self.widget.winfo_width()*0.5
        #x = x + tw.winfo_pointerx()
        y = y + cy + self.widget.winfo_rooty() +\
                     self.widget.winfo_height() + 2
        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d"%(x,y))
        label = Label(tw, text=self.text, justify=LEFT,background="#ffffe0", 
                      relief=SOLID, borderwidth=1,font=("tahoma", "8",
                      "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw: 
            tw.destroy()



def rungui():
    root = Tk()
    root.resizable(0,0)
    app = Application(root)
    scrollbar = Scrollbar(root)
    scrollbar.grid(column=3,row=0,sticky=N+S)
    outtext = Text(root,wrap=WORD,bg="white",yscrollcommand=scrollbar.set)
    outtext.grid(column=1,row=0,sticky=N+S,columnspan=2)
    scrollbar.config(command=outtext.yview)

    class NewStdout(object):
        def __init__(self,tkbox,f,sbar):
            self.tkbox = tkbox
            self.f = f
            self.sbar = sbar
            self.tkbox.tag_config("warning",background="yellow2")
            self.tkbox.tag_config("error",background="firebrick1")
            self.tkbox.tag_config("finished",background="lawn green")
            self.tkbox.tag_config("signal",background="black",
                                  foreground="white")
        def write(self,txt):
            tags = None
            for msg in ["WARNING","ERROR"]:
                if txt.startswith(msg):
                    tags = (msg.lower())
                    break
            if txt.startswith(("TERMINATE","KILL")):
                tags = ("signal",) 
            if txt.endswith(("run-subpipe finished!",
                            "run-photpipe finished!",
                            "EXITING")):
                tags = ("finished",)

            if txt.startswith("attempt "):
                pass
                #self.tkbox.insert(END,txt.split("\r")[-1],tags)
                #if self.lineno == None:
                #    self.lineno = int(self.tkbox.index('end').split('.')[0])-1
                #    first = True
                
                #self.tkbox.delete("%d.0" % self.lineno,"%d.90" % self.lineno)
                #self.tkbox.insert(END,txt.split("\r")[0]+"\n",tags)
                #if first:
                #    self.lineno -= 1
                #    first = False
            else:
                #self.lineno = None
                # sometimes throws ValueError due to accessing from two threads
                try:
                    sbarposition = self.sbar.get()[1]
                except ValueError:
                    sbarposition = 0.0
                self.tkbox.insert(END,txt,tags)
                if sbarposition == 1.0:
                    try:
                        self.tkbox.yview(MOVETO,1.0)
                    except TclError:
                        pass
                
            self.f.flush()
        def __getattr__(self, attr):
            return getattr(self.f, attr)


    sys.stdout = NewStdout(outtext,sys.stdout,scrollbar)

    def selectall(event):
        event.widget.tag_add("sel","1.0","end")
    root.bind_class("Text","<Control-a>",selectall)

    app.master.title("CLASP")
    root.mainloop()



if __name__ == "__main__":
    rungui()

