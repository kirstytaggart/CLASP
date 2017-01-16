# ISIS params (http://www2.iap.fr/users/alard/sub.html)
# used by subpipe.subtraction(). 
# reverseflag passed as an explicit argument in run-subpipe.

# the program can attempt to tailor the following params under poor seeing to,
# hopefully, achieve a better subtraction. set `adapt` to False if you wish
# to explicitly only use the values immediately below.
adapt = True
##############
# ADAPT PARAMS
##############
hms = 9     # half mesh size
hss = hms+6 # half stamp size (hms+6 is a good value)
sg1 = 0.9   #
sg2 = 1.5   # sigma widths of gaussians to use
sg3 = 2.5   #
##############
# END
##############

# saturation level
si = 50000  # image
st = 50000  # template

# num stamps to use in x and y directions (should be varied with num objects)
nsx = 9
nsy = 9

# order of kernel, reduce if low number of objects in the field
kernelorder = 2

# minimum value to fit (too low is better than too high)
minval = 5

# minimum central value for a stamp (~faint source peak value, again, be
# conservative)
minstamp = 130

# number of image subsections along each axis. must be > 0
sx = 1
sy = 1

# remove convolved image? (if not will be saved in your workdir as *.conv.fits
removeconv = 1

# degree of function to fit to background (probably fits a polynomial)
deg_bg = 2

# god knows...
iterkernelsig = 2 

# own stamps files, if required, should be offered on the command line and 
# the pipeline will take care of it from there

