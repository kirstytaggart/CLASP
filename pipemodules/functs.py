import datetime

import numpy as np


def get_obsdate(header,obsdatekeys):
    """
    Attempts to find a float value for each of the header keys in obsdatekeys,
    returning the first one that satisfies this requirement or False if none
    do
    """
    date = False
    for kw in obsdatekeys:
        try:
            date = float(header[kw])
        except KeyError, ValueError:
            date = False
        else:
            break

    if not date:
        return ''
    else:
        return date



def get_filt(header,filterkeys):
    """
    Finds filter for an observation given a header. Searches multiple headers,
    and returns the first non 'clear' value found from the given filterkeys
    """
    # Needs work to make universal
    filt = False
    for kw in filterkeys: 
        try:
            filt = header[kw]
            if filt.lower() == 'clear':
                filt = False
                continue
            elif not filt.lower():
                filt = False
                continue
            else: 
                break
        except KeyError:
            filt = False        

    SDSSdic = {'SDSS-U':'u',
               'SDSS-G':'g',
               'SDSS-R':'r',
               'SDSS-I':'i',
               'SDSS-Z':'z'}
    if not filt:
        return ''

    for key in SDSSdic.keys():
            if filt == key: filt = SDSSdic[key]
    return filt


def get_stats(data,rmzeros = False):
    """
    Data must be an array. rmzeros flag used to remove all zero value pixels.
    Returns a dictionary of image stats such as mean,stddev etc.
    """
    try:
        ysize,xsize = data.shape
    except ValueError:
        ysize = data.shape[0]
        xsize = 1

    if rmzeros:
        data = data[data!=0]

    #compute full array stddev
    tstddev = np.std(data)

    #compute 3sigma clip stats
    data3 = data.copy()
    for i in range(2):
        stddev = np.std(data3)
        mean = np.sum(data3)/len(data3.ravel())
        #remove any values >3sigma from mean
        clipmin = mean - 3 * stddev
        clipmax = mean + 3 * stddev
        #clip data
        data3 = data3[data3>clipmin] #returns ravelled array anyway
        data3 = data3[data3<clipmax]

    if len(data3) < float(xsize*ysize)/100:
        print 'WARNING clipped data is small, using total data stats'
        data3 = data

    #define mean/stddev of clipped data
    stddev = np.std(data3)
    mean = np.sum(data3)/len(data3.ravel())
    datamin = mean - 5*stddev

    return {'xsize':xsize,'ysize':ysize,'mean':mean,
            'stddev':stddev,'tstddev':tstddev,'datamin':datamin}

def get_datetime():
    """
    return a user readable version of the current datetime
    """
    now = datetime.datetime.now()
    return now.strftime('%H:%M %a %d %B %Y')
