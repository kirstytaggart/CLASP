#! /usr/bin/env python2.7

#TODO dont close down ds9 inbetween objcoo and starnums if starslist not defined
#TODO open ds9 silently
#TODO see auto_make_starlist in photpipe. How to have program select good stars
#TODO make opening ds9 a function inside photpipe
#TODO make answer y/n function in pipemodules.functs? while True: if answe...
#TODO if cog model fails, just do direct large aperture photometry of object?
#TODO if smallap !< largeap then warn user and just use largeap or something?
#     i.e. skip cog model for aperture correction.
#TODO try open ds9, if fails then open ds9 packaged with CLASP in pipemods/ds9

import sys
import os
import argparse
import shelve
import logging
import datetime
from glob import glob

import subpipe
import photpipe
import pipemodules.functs as functs

LCFILENAME = 'lightcurve.txt'
REPORTNAME = 'photpipe_report.txt'
LOGNAME = 'photpipe_log.txt'
SHELVENAME = 'pipe.shelve' 

class MyParser(argparse.ArgumentParser):
    """
    wrapper for argparse.ArgumentParser

    custom error behaviour - will automatically show full help on argument
    error
    """
    def error(self, message):
        sys.stderr.write('ERROR: %s\n' % message)
        self.print_usage()
        sys.stderr.write('type -h or --help to display full help\n')
        sys.exit(2)

class FlushFile(object):
    """
    custom stdout behaviour - flush stdout after every write.
    helps with gui
    """
    def __init__(self, f):
        self.f = f
    def write(self, x):
        self.f.write(x)
        self.f.flush()
    def flush(self):
        self.f.flush()

# Assign stdout to our custom class
sys.stdout = FlushFile(sys.stdout)

class CallPhotometryPipeline(object):
    """
    user side class to call on photpipe

    """

    def __init__(self,args):

        self.workdir = os.path.abspath(args.workdir)
        self.shelvefilepath = os.path.join(self.workdir,SHELVENAME)
        self.smallap = args.smallap
        self.largeap = args.largeap
        self.objcoords = args.objcoords
        self.clobber = args.clobber
        self.autopick = args.autopick

        logger.info('CREATED: %s' % functs.get_datetime())

        if not self.objcoords:
            logger.debug('getting object pixel coordinates')
            self.objcoords = photpipe.get_object_coords(self.workdir)
        if not self.objcoords:
            logger.error('couldn\'t obtain object pixel coordinates')
            sys.exit(3)
        else:
            logger.info('object coordinates x,y: %s' % self.objcoords) 

        logger.info('creating lightcurve file: %s' % REPORTNAME)
        self.create_lightcurvefile()
        logger.info('creating report file: %s' % REPORTNAME)
        self.create_report()

        logger.debug('entering main loop')
        for self.instance,num in self.get_next_instance():
            logger.info('\n'+'-'*79+'\n(%i/%i) processsing image: %s\n'
                        % (num,self.numinst,self.instance.image)+'-'*79)
            logger.debug('executing %s in workdir' % self.instance.PIPEcfg)
            photpipe.execpipecfg(self.workdir,self.instance.PIPEcfg)
            logger.debug('calling photpipe.PhotometryPipeline')
            self.p = photpipe.PhotometryPipeline(self.instance,
                                                 self.objcoords,
                                                 smallap = self.smallap,
                                                 largeap = self.largeap,
                                                 autopick = self.autopick)
            logger.debug('writing to lightcurve file')
            self.write_lightcurve_line()
            logger.debug('writing to report')
            self.write_report_line()

        logger.debug('finished main loop!\n\n')

        logger.info('run-photpipe finished!\n')


    def get_next_instance(self):
        # grab all the subpipe instances found in the workdir shelve
        logger.debug('opening shelve file')
        self.shv = shelve.open(self.shelvefilepath)
        self.numinst = len(self.shv)
        logger.info('%i subpipe instances to process' % self.numinst)
        if self.clobber:
            logger.debug('removing previous template photometry files')
            for ext in ['starcoo','apcorphot','apcor','mkap']:
                extfiles = glob(os.path.join(self.workdir,'template/*.'+ext))
                for f in extfiles:
                    try:
                        os.remove(f)
                    except OSError:
                        logger.warning('removing of %s failed' % f)
            
        # if the instance didn't fail in subtraction, yield it
        i = 0
        for image in sorted(self.shv):
            i += 1
            instance = self.shv[image]
            if not isinstance(instance,subpipe.SubtractionPipeline):
                logger.error('\n'+'-'*79+'\ninstance found (%s) not of '
                             'subpipe.SubtractionPipeline, skipping' 
                             % (instance)+'-'*79)
                continue     
            if instance.fail: #FIXME is not None
                logger.warning('\n'+'-'*79+'\n%s failed (code %i) in subpipe,'
                               ' skipping\n' % (image,instance.fail)+'-'*79)
                continue
            yield instance,i


    def create_report(self):
        with open(os.path.join(workdir,REPORTNAME),'w') as rpt:
            now = datetime.datetime.now()
            rpt.write('# Report file created %s\n'
                      '# working directory = %s\n'
                      '# small aperture = %i\n'
                      '# large aperture = %i\n'
                      '# object coords = %s\n\n'
                       % (now.strftime('%H:%M %a %d %B %Y'),
                          self.workdir,self.smallap,self.largeap,
                          self.objcoords))
            rpt.write('-'*122+'\n')
            rpt.write('{0:<29} {1:>10} {2:>5} {3:>10} {4:>5} '
                      '{5:>12} {6:>5} {7:>6} {8:>10}  {9:>5} '
                      '{10:>12} {2:>5}\n'.format(
                      'Image','Objmag_sm','err','Apcor','err','Objmag_lrg',
                      'err','Stars','Offset','err','Objmag_off','err'))
            rpt.write('-'*122)



    def create_lightcurvefile(self):
        with open(os.path.join(workdir,LCFILENAME),'w') as lc:
            now = datetime.datetime.now()
            lc.write('# Lightcurve file created %s\n#\n'
                     % now.strftime('%H:%M %a %d %B %Y'))
            lc.write('#'+'-'*60+'\n')
            lc.write('#{0:<29} {1:>10} {2:>11} {3:>7}\n'.format(
                     'Image','ObsDate','Magnitude','error'))
            lc.write('#'+'-'*60)


    def write_lightcurve_line(self):
        l = self.p.get_lightcurve_info()
        if isinstance(l,dict):
            with open(os.path.join(workdir,LCFILENAME),'a') as lc:
                lc.write('\n{0:<29} {1:<10.5f} {2:>11.3f} {3:>7.3f}'.format(
                     l['image'],l['obsdate'],l['objmag'],l['objmagerr']))
        else:
            with open(os.path.join(workdir,LCFILENAME),'a') as lc:
                lc.write('\n#{0:<29} failed (code {1})! See log for details'
                     .format(l[0],l[1]))
        
            
    
    def write_report_line(self):
        r = self.p.get_report_info()
        if isinstance(r,dict): #dont need place specifiers if in order! VVV
            with open(os.path.join(workdir,REPORTNAME),'a') as rpt:
                rpt.write('\n{0:<29} {1:10.3f} {2:5.3f} {3:10.3f} {4:5.3f} '
                          '{5:12.3f} {6:5.3f} {7:>6} {8:10.3f}  {9:5.3f} '
                          '{10:12.3f} {11:5.3f}'.format(
                          r['image'][:29],r['objmag_sm'],r['objmagerr_sm'],
                          r['apcor'],r['apcorerr'],r['objmag_lrg'],
                          r['objmagerr_lrg'],r['numoffsetstars'],r['offset'],
                          r['offseterr'],r['objmag_off'],r['objmagerr_off']))
        else:
            with open(os.path.join(workdir,REPORTNAME),'a') as rpt:
                rpt.write('\n#{0:<29} failed (code {1})! See log for '
                          'details'.format(r[0],r[1]))


if __name__ == '__main__':

    parser = MyParser(description='Photometry pipeline for'
                                  ' transient observations.')
    parser.add_argument('workdir', type=str, help='path to the working'
                        ' directory where subpipe work was output')
    parser.add_argument('-c',dest='clobber',action='store_true',
                        help='Clobber over existing photometry work in \
                              `workdir`')
    parser.add_argument('-sa',dest='smallap',type=int,default=3,
                        help='radius (in pixels) of small object aperture'
                              ' (default: 3)')
    parser.add_argument('-la',dest='largeap',type=int,default=15,
                        help='radius (in pixels) of large object aperture'
                        ' to correct to (default: 15)')
    parser.add_argument('-o',dest='objcoords',type=str,default=None,
                        help='pixel coordinates of object in subtracted '
                              'frames as a string "x,y" e.g. -o "123,456". If'
                              ' omitted program will display frame and ask '
                              'for input.')
    parser.add_argument('-a',dest='autopick',action='store_true',
                        help='bypass automated star selection, manually'
                        ' select stars for aperture correction and offset. '
                        'invokes -n to overwrite any existing list')
    parser.add_argument('-d',dest='debug', action='store_true', default=False,
                        help='output all debug messages (i.e. run verbose), '
                        'logfile has verbosity `debug`')
    
    args = parser.parse_args()

    print 'INFO\tchecking argument sanity'
    # check if workdir exists
    workdir = args.workdir
    if not os.path.isdir(workdir):
        print 'ERROR\tworkdir does not exist! (%s)' % os.path.abspath(workdir)
        sys.exit(2)
    # check that workdir has a 'template' directory
    try:
        open(os.path.join(workdir,SHELVENAME))
    except:
        print 'ERROR\tsubpipe shelve (%s) cannot be opened! check it exists.'\
              % os.path.join(workdir,SHELVENAME)
        sys.exit(2)
    # check if there is an existing lightcurve file if we don't have 
    # permission to overwrite it.
    clobber = args.clobber
    lcfile = glob(os.path.join(workdir,LCFILENAME))
    if len(lcfile) != 0 and not clobber:
        print 'ERROR\tlightcurve file (%s) exists and clobber is False.'\
               % os.path.join(workdir,LCFILENAME)
        sys.exit(2)

    #check objcoords is in correct format
    objcoords = args.objcoords
    if objcoords and len(objcoords.split(',')) != 2:
        print 'ERROR\tobjcoords must be a string of the format: "x,y"'
        sys,exit(2)

    # set up loggers
    # global logger
    logger = logging.getLogger('run-photpipe')
    logger.setLevel(logging.DEBUG)
    f = logging.Formatter('%(levelname)s\t%(module)s - %(message)s')
    # handler to write log entries to file
    h1 = logging.FileHandler(os.path.join(args.workdir,LOGNAME))
    h1.setLevel(logging.DEBUG)# if args.debug else h1.setLevel(logging.INFO)
    h1.setFormatter(f)
    logger.addHandler(h1)
    # handler to write log entries to terminal
    h2 = logging.StreamHandler(stream=sys.stdout)
    h2.setLevel(logging.DEBUG) if args.debug else h2.setLevel(logging.INFO)
    h2.setFormatter(f)
    logger.addHandler(h2)
    
    # run the subtraction pipeline
    CallPhotometryPipeline(args)
