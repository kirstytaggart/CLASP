#! /usr/bin/env python

#TODO rewrite align_images - allow it to pass to tolerance matching if no
#     objects match in SEARCHRAD to template
#     use more fits headers (i.e. GAIN)
#TODO add as a sub function to align_images the xyfail and `retval =
#     None if wfail else outimage` and logger error to keep it DRY
#TODO remove instance in pipe.shelve before doing anything with updating
#     to prevent half over-written instances
#TODO make numobj an attribute of subtraction instance but need to still
#     define it for all even when not making tempcoo
#TODO ensure SExtracting using a good threshold, and how to pass tempthresh
#     when it's only defined on first image running through?
#TODO use iraf.task.saveParList(filename="task.par") for all tasks used where
#     a default is used and load with iraf.task.setParList("task.par") such
#     that user can alter if required
#TODO change all 'work directory' references to 'output directory' to be a bit
#     clearer this is where the final products are.
#TODO allow template to be MEF and when copying it across to template/ then
#     just copy the required data/header
#TODO getstats and alardwrap need to work better together to stop running
#     SExtractor 4 times. thresh should be passed to get stats instead of
#     thresh = 10 hardcoded.
#TODO make wregister fallback method if xyxymatch fails instead of wreg first

import sys
import os
import shutil
import argparse
import shelve
import logging
import subprocess
import filecmp
from glob import glob

import pipemodules.functs as functs

ISISCONFIG = 'ISIScfg.py'
PIPECONFIG = 'PIPEcfg.py'
REPORTNAME = 'subpipe_report.txt'
LOGNAME = 'subpipe_log.txt'
SHELVENAME = 'pipe.shelve'

# the file and directory path to this script: in case you call it from 
# another directory, the relative paths to the script are still intact
FILEPATH = os.path.realpath(__file__)
FILEDIR = os.path.dirname(FILEPATH)

class MyParser(argparse.ArgumentParser):
    """
    wrapper for argparse.ArgumentParser

    custom error behaviour - will automatically show usage help on argument
    error
    """
    def error(self, message):
        sys.stderr.write('ERROR\t%s\n' % message)
        self.print_usage()
        sys.stderr.write('type -h or --help to display full help\n')
        sys.exit(2) 

class FlushFile(object):
    """
    custom stdout behaviour
    
    this will flush stdout after every write - helps with output to gui
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


class CallSubtractionPipeline(object):
    """
    user side class to call on subpipe

    handles the individual calling of subpipe for each image in the imagelist
    created from the command line.
    args is passed from command line parsing
    """

    def __init__(self,args,imagelist):

        import subpipe

        # assign command line arguments as class attributes
        self.imagedir = os.path.abspath(args.imagedir)
        self.imagelist = imagelist
        self.template = os.path.abspath(args.template)
        self.workdir = os.path.abspath(args.workdir)
        self.selection = args.selection
        self.fringeframe = args.fringeframe
        self.bpm = args.badpixelmask
        self.trim = args.trim
        self.reverseflag = args.reverseflag
        self.update = args.update
        self.cleantemplate = args.cleantemplate
        self.temp_iter = args.temp_iter
        self.image_iter = args.image_iter
        self.ISIScfg = args.ISIScfg
        self.PIPEcfg = args.PIPEcfg
        if args.stamps != '':
            self.stamps = os.path.abspath(args.stamps)
        else:
            self.stamps = args.stamps

        if self.update:
            logger.info('LOG FILE UPDATED - %s' % functs.get_datetime())
        else:
            logger.info('LOG FILE CREATED - %s' % functs.get_datetime())

        self.create_report()

        # define the template variable to the new path of the template in
        # the `template` sub directory of workdir
        newtemplatepath = os.path.join(self.workdir,'template/')+\
                          os.path.basename(self.template)
        try:
            # check if we've already got the template in place
            open(newtemplatepath)
        except IOError:
            # if the template isn't already there, copy it
            logger.info('copying template to %s' 
                        % os.path.join(self.workdir,'template'))
            shutil.copy(self.template,newtemplatepath)
        finally:
            self.template = newtemplatepath

        # copy ISIScfg and PIPEcfg to the work directory
        logger.debug('copying config files to workdir')
        newcfgfiles = []
        if self.update:
            # if we're updating, the config files may have been altered
            # we try to copy over the first unique *.[n].py suffix, unless
            # we encounter a file with the same content, in which case use
            # that as the config file to use
            for cfgfile in [self.ISIScfg,self.PIPEcfg]:
                newcfgfile = os.path.join(self.workdir,
                                           os.path.basename(cfgfile))
                # test if the current config file is the same as original
                # config file used for the workdir
                same = filecmp.cmp(cfgfile,newcfgfile)
                if same:
                    newcfgfiles.append(newcfgfile)
                    continue
                # if not, iterate through *.[n].py suffixes until we find
                # an equal file or a unique filename
                basepath = os.path.splitext(newcfgfile)[0]
                for j in range(1,30):
                    jpath = basepath+'.'+str(j)+'.py'
                    try:
                        open(jpath)
                    except:
                        shutil.copy(cfgfile,jpath)
                        newcfgfiles.append(jpath)
                        break
                    else:
                        same = filecmp.cmp(cfgfile,jpath)
                        if same:
                            newcfgfiles.append(jpath)
                            break
                    if j == 29:
                        logger.error('too many unique config files\
                                      in workdir. start a new workdir')
                        sys.exit(3)

        else:
            for cfgfile in [self.ISIScfg,self.PIPEcfg]:
                newcfgfile = os.path.join(self.workdir,
                                           os.path.basename(cfgfile))
                shutil.copy(cfgfile,newcfgfile)
                newcfgfiles.append(newcfgfile)

        # reassign config file variables to newly copied versions
        self.ISIScfg,self.PIPEcfg = newcfgfiles
        logger.debug('PIPE config file: %s' % self.PIPEcfg)
        logger.debug('ISIS config file: %s' % self.ISIScfg)

        # copy stamps file to work directory if required
        if self.stamps:
            logger.debug('copying stamps file to workdir')
            try:
                shutil.copy(self.stamps,self.workdir)
            except (IOError,OSError):
                logger.exception('couldn\'t copy stamps file to work'
                                 ' directory')
                sys.exit(1)
            else:
                self.stamps = os.path.join(self.workdir,
                                           os.path.basename(self.stamps))

        # if we're updating, we don't want to clean template as it will 
        # already be done form previous work
        if self.update:
            logger.debug('cancelling template cleaning - in update mode')
            self.cleantemplate = False
            self.temp_iter = 0

        logger.debug('entering main loop')
        for self.image,num in self.get_next_image():
            logger.info('\n'+'-'*79+'\n(%i/%i) processsing image: %s\n'
                        % (num,self.numimages,self.image)+'-'*79)
            logger.debug('executing %s' % self.PIPEcfg)
            subpipe.execpipecfg("",self.PIPEcfg)
            logger.debug('calling subpipe.SubtractionPipeline')
            self.s = subpipe.SubtractionPipeline(self.image,
                                                 self.template,
                                                 self.fringeframe,
                                                 self.bpm,
                                                 self.trim,
                                                 self.image_iter,
                                                 self.reverseflag,
                                                 self.ISIScfg,
                                                 self.PIPEcfg,
                                                 self.stamps,
                                                 self.cleantemplate,
                                                 self.temp_iter)
            logger.debug('subpipe.SubtractionPipeline finished')

            self.s.make_pngs()
            self.write_report_line()
            self.write_to_shelve()

        logger.debug('finished main loop')

        logger.info('run-subpipe finished!\n')
        

    def get_next_image(self):
        # grab all raw image paths
        self.numimages = len(self.imagelist)
        logger.debug('found %s image(s) to process' % self.numimages)     

        # copy raw images to workdir one at a time and yield them
        for i,rawimage in enumerate(self.imagelist,1):
            logger.debug('copying image %i to workdir' % i)
            shutil.copy(rawimage,self.workdir)
            yield os.path.join(self.workdir,os.path.basename(rawimage)),i


    def create_report(self):
        logger.debug('creating report file in workdir - %s' % REPORTNAME)
        with open(os.path.join(self.workdir,REPORTNAME),'a') as rpt:
            # when updating previous work, just add a line to existing report
            if self.update:
                rpt.write('\n# UPDATING previous work: %s...'
                          % functs.get_datetime())
                return
            rpt.write('# REPORT FILE CREATED - %s\n'
                      '# image directory = %s\n'
                      '# working directory = %s\n'
                      '# template = %s\n'
                      '# clean template = %s\n'
                      '# fringe frame = %s\n'
                      '# bad pixel mask = %s\n'
                      '# trim pixel border = %s\n'
                      '# template cleaning iterations = %s\n'
                      '# image cleaning iterations = %s\n'
                      '# reverseflag = %s\n'
                      '# stamps file = %s\n'
                      '# PIPE config file = %s\n'
                      '# ISIS config file = %s\n\n' 
                      % (functs.get_datetime(),self.imagedir,
                         self.workdir,self.template,self.cleantemplate,
                         self.fringeframe,self.bpm,self.trim,self.temp_iter,
                         self.image_iter,self.reverseflag,self.stamps,
                         self.PIPEcfg,self.ISIScfg))
            rpt.write('-'*160+'\n')
            rpt.write('{0:<29} {1:<7} {2:>6} {3:>7} {4:>9} {5:>10} {6:>15} '
                      '{7:>11} {8:>7} {9:>7} {10:>9} {11:>11} {12:>10} '
                      '{13:>8}\n'.format(
                      'Image','Object','iFWHM','iSTDDEV','tempFWHM',
                      'tempSTDDEV','Aligned','Seeingratio','Reverse',
                      'subMEAN','subSTDDEV','subTSTDDEV','sum_kernel',
                      'failcode'))
            rpt.write('-'*160+'\n')


    def write_report_line(self):
        logger.debug('writing to report')
        r = self.s.get_report_info()
        with open(os.path.join(self.workdir,REPORTNAME),'a') as rpt:
            rpt.write('\n{0:<29} {1:<8} {2:6.3f} {3:7.3f} {4:9.3f} {5:10.3f} '
                      '{6:>15} {7:11.3f} {8:>7} {9:>7.3f} {10:>9.3f} '
                      '{11:>11.3f} {12:>10} {13:>8}'.format(
                      r['image'][:29],r['object'][:8],r['ifwhm'],r['istddev'],
                      r['tfwhm'],r['tstddev'],r['aligned'],r['seeingratio'],
                      r['reverse'],r['submean'],r['substddev'],
                      r['subtstddev'],r['sum_kernel'],r['failcode']))


    def write_to_shelve(self):
        logger.debug('writing to shelve')
        self.shv = shelve.open(os.path.join(self.workdir,SHELVENAME))
        shelvekey = os.path.basename(self.image)
        self.shv[shelvekey] = self.s
        self.shv.close()





if __name__ == '__main__':

    parser = MyParser(description='Subtraction pipeline for'
                                  ' transient observations')
    parser.add_argument('imagedir', type=str, help='path to a directory'
                        ' containing image(s) to be processed or file path to'
                        ' a single image to process')
    parser.add_argument('template', type=str, help='file path to the template'
                        ' file')
    parser.add_argument('workdir', type=str, help='path to a working'
                        ' directory to store all pipeline output (asks to '
                        'remove if directory exists)')
    parser.add_argument('-s', dest='selection', default='*.fits',
                        help='selection pattern for files in `imagedir` '
                        '(default: "*.fits")')
    parser.add_argument('-u',dest='update',action='store_true',
                        help='update `workdir` without destroying previous '
                        'work, use to add new observations/overwrite old '
                        'pipeline output where output is poor')
    parser.add_argument('-f',dest='fringeframe', type=str, help='file path to'
                        ' the fringeframe for observations, if required')
    parser.add_argument('-b',dest='badpixelmask', type=str, help='file path '
                        'to the bad pixel mask for observations, if required')
    parser.add_argument('-c',dest='cleantemplate', action='store_true', help=
                        'clean template using fringeframe and bad pixel mask,'
                        ' as supplied. cosmic ray removal determined by -ti')
    parser.add_argument('-ti',dest='temp_iter', type=int, default=2,
                        help='number of cosmicray detection iterations to run'
                        ' on the template, set as zero to skip (default: 2)')
    parser.add_argument('-ii',dest='image_iter', type=int, default=2,
                        help='number of cosmicray detection iterations to run'
                        ' on the image(s), set as zero to skip (default: 2)')
    parser.add_argument('-t',dest='trim', type=int, default=0, 
                        help='border in pixels to fix to zero around images'
                        ' (default: 0)')
    parser.add_argument('-r',dest='reverseflag', type=int, default=0,
                        help='ISIS subtraction direction - 0: let program try'
                        ' decide best subtraction 1: reverse subtraction '
                        'direction chosen by program 2: always convolve image'
                        ' 3: always convolve template (default: 0)')
    parser.add_argument('-stamps',dest='stamps', type=str, default='',
                        help='file path to text file containing the x y '
                        'coordinates of the stamps to use by ISIS '
                        'in columns 1 and 2 respectively, ISIS '
                        'will use these instead of finding its own')
    parser.add_argument('-d',dest='debug', action='store_true',
                        help='output all debug messages (i.e. run verbose), '
                             'logfile has verbosity `debug`automatically')
    
    args = parser.parse_args()

    print 'INFO\tchecking argument sanity'

    # check imagedir is a directory or a file and generate list of images
    if os.path.isdir(args.imagedir):
        imagelist = sorted(glob(os.path.join(os.path.abspath(args.imagedir),
                                             args.selection)))
    elif os.path.isfile(args.imagedir):
        imagelist = [args.imagedir]
    else:
        print 'ERROR\timagedir (%s) is not a file or directory!'\
              % os.path.abspath(args.imagedir)
        sys.exit(2)

    # check there will be images to process:
    if len(imagelist) == 0:
        print 'ERROR\tno images in imagedir (%s) matching selection, "%s"!'\
              % (args.imagedir,args.selection)
        sys.exit(2)

    # check template exists
    if not os.path.isfile(args.template):
        print 'ERROR\ttemplate file (%s) doesn\'t exist!'\
              % os.path.abspath(args.template)
        sys.exit(2)

    # if specified, check that bpm/fringeframe exist
    if args.fringeframe and not os.path.isfile(args.fringeframe):
        print 'ERROR\tfringeframe file (%s) doesn\'t exist!'\
              % os.path.abspath(args.fringeframe)
        sys.exit(2)
    if args.badpixelmask and not os.path.isfile(args.badpixelmask):
        print 'ERROR\tbad pixel mask (%s) doesn\'t exist!'\
              % os.path.abspath(args.badpixelmask)
        sys.exit(2)

    # check number of cleaning iterations are valid
    if args.temp_iter < 0:
        print 'WARNING\tsetting template cleaning iterations to 0'
        args.temp_iter = 0
    if args.image_iter < 0:
        print 'WARNING\tsetting image cleaning iterations to 0'
        args.image_iter = 0

    # check trim value is valid
    if args.trim < 0:
        print 'WARNING\tsetting trim to 0'
        args.trim = 0
        
    # check PIPE and ISIS config files exist
    ISIScfgpath = os.path.join(FILEDIR,ISISCONFIG)
    if not os.path.isfile(ISIScfgpath):
        print 'ERROR\tISIS config file (%s) doesn\'t exist!'\
               % ISIScfgpath
        sys.exit(2)
    PIPEcfgpath = os.path.join(FILEDIR,PIPECONFIG)
    if not os.path.isfile(PIPEcfgpath):
        print 'ERROR\tPIPE config file (%s) doesn\'t exist!'\
               % PIPEcfgpath
        sys.exit(2)
    # then assign them as args variables
    args.ISIScfg = ISIScfgpath
    args.PIPEcfg = PIPEcfgpath

    # check if reverseflag param is legal
    if args.reverseflag < 0 or args.reverseflag > 3:
        print 'ERROR\treverseflag must be 0-3, see -h for options.'
        sys.exit(2)

    # check stamps file exists
    if args.stamps and not os.path.isfile(args.stamps):
        print 'ERROR\tstamps file (%s) doesn\'t exist!'\
              % os.path.abspath(args.stamps)
        sys.exit(2)

    # check that the workdir exists if the user is updating previous work
    if args.update and not os.path.isdir(args.workdir):
        print 'ERROR\tif you\'re updating previous work, workdir must exist!'
        sys.exit(2)

    # if the workdir exists, check with user whether to remove
    if os.path.isdir(args.workdir) and not args.update:
        print 'WARNING\tworkdir (%s) already exists!'\
              % os.path.abspath(args.workdir)
        while True:
            answer = raw_input('QUERY\tdo you want to delete workdir? (y/n)\n')
            if answer == 'y':
                try:
                    shutil.rmtree(args.workdir)
                except OSError:
                    # if we can't remove, probably got a file open somewhere
                    print ('ERROR\tcouldn\'t remove all files from workdir. '
                           'one or more of the files perhaps in use.\n '
                           'try use `lsof`')
                    sys.exit(1)
                else:
                    print 'INFO\tworkdir has been removed'     
                    break        
            elif answer == 'n':
                print 'EXITING (workdir already in use)'
                sys.exit(0)

    # make the workdir if needed
    if not os.path.isdir(args.workdir):
        os.makedirs(os.path.join(args.workdir,'template'))

    # set up loggers
    # global logger
    logger = logging.getLogger('run-subpipe')
    logger.setLevel(logging.DEBUG)
    f = logging.Formatter('%(levelname)s\t%(module)s - %(message)s')
    # handler to write log entries to file
    h1 = logging.FileHandler(os.path.join(args.workdir,LOGNAME))
    h1.setLevel(logging.DEBUG) # logfile will always have debug verbosity
    h1.setFormatter(f)
    logger.addHandler(h1)
    # handler to write log entries to terminal
    h2 = logging.StreamHandler(sys.stdout)
    h2.setLevel(logging.DEBUG) if args.debug else h2.setLevel(logging.INFO)
    h2.setFormatter(f)
    logger.addHandler(h2)
    
    # run the subtraction pipeline
    CallSubtractionPipeline(args,imagelist)
