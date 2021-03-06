#!/usr/bin/python

# Stripped down version of v2 script, does not try to guess/calibrate for R.
# R value can be set separately and the center tap seems not to be that precise anyway.

# Quick cheat sheet for manual L and R adjustments:
# - Increase R if center is higher than edges (dome)
# - Decrease R if center is lower than edges (bowl)
# - Increase L if print is too large
# - Decrease L if print is too small

# Updated version of the original script
# Most of the changes are just to restructure code
# Main functionality additions are handling of serial errors and support for additional arguments
# Tested on Ubuntu 16.02 with Python2.7, Windows 2016 Server with Python3.6 and MacOS High Sierra with Python2.7

from serial import Serial, SerialException, PARITY_ODD, PARITY_NONE
import sys
import argparse
import json

def establish_serial_connection(port, speed=115200, timeout=10, writeTimeout=10000):
    # Hack for USB connection
    # There must be a way to do it cleaner, but I can't seem to find it
    try:
        temp = Serial(port, speed, timeout=timeout, writeTimeout=writeTimeout, parity=PARITY_ODD)
        if sys.platform == 'win32':
            temp.close()
        conn = Serial(port, speed, timeout=timeout, writeTimeout=writeTimeout, parity=PARITY_NONE)
        conn.setRTS(False)#needed on mac
        if sys.platform != 'win32':
            temp.close()
        return conn
    except SerialException as e:
        print ("Could not connect to {0} at baudrate {1}\nSerial error: {2}".format(port, str(speed), e))
        return None
    except IOError as e:
        print ("Could not connect to {0} at baudrate {1}\nIO error: {2}".format(port, str(speed), e))
        return None

def get_current_values(port):

    # This function makes lots of assumptions about the output of the printer,
    # but I am not sure if writing it in regex or improving it any other way would make any difference
    # as this is unique for printer with this code and may not work for anything else

    port.write(('G28 X0 Y0\n').encode())
    port.write(('G29 P1 V4\n').encode())

    while True:
        out = port.readline().decode()
        if 'G29 Auto Bed Leveling' in out:
            break

    out = port.readline().decode()
    z_axis_1 = out.split(' ')
    out = port.readline().decode()
    z_axis_2 = out.split(' ')
    z_ave = float("{0:.3f}".format((float(z_axis_1[6]) + float(z_axis_2[6])) / 2))
    print('Z-Pillar :{0}, {1} Average:{2}'.format(z_axis_1[6].rstrip(),z_axis_2[6].rstrip(),str(z_ave)))

    out = port.readline().decode()
    x_axis_1 = out.split(' ')
    out = port.readline().decode()
    x_axis_2 = out.split(' ')
    x_ave = float("{0:.3f}".format((float(x_axis_1[6]) + float(x_axis_2[6])) / 2))
    print('X-Pillar :{0}, {1} Average:{2}'.format(x_axis_1[6].rstrip(),x_axis_2[6].rstrip(),str(x_ave)))

    out = port.readline().decode()
    y_axis_1 = out.split(' ')
    out = port.readline().decode()
    y_axis_2 = out.split(' ')
    y_ave = float("{0:.3f}".format((float(y_axis_1[6]) + float(y_axis_2[6])) / 2))
    print('Y-Pillar :{0}, {1} Average:{2}'.format(y_axis_1[6].rstrip(),y_axis_2[6].rstrip(),str(y_ave)))

    return x_ave, y_ave, z_ave

def determine_error(x_ave, y_ave, z_ave):
    max_value = max([x_ave, y_ave, z_ave])
    x_error = float("{0:.4f}".format(x_ave - max_value))
    y_error = float("{0:.4f}".format(y_ave - max_value))
    z_error = float("{0:.4f}".format(z_ave - max_value))
    print('X-Error: ' + str(x_error) + ' Y-Error: ' + str(y_error) + ' Z-Error: ' + str(z_error) + '\n')
    return x_error, y_error, z_error

def calibrate(port, x_error, y_error, z_error, trial_x, trial_y, trial_z, max_runs, runs):
    calibrated = True

    if abs(x_error) >= 0.02:
        new_x = float("{0:.4f}".format(x_error + trial_x)) if runs < (max_runs / 2) else float("{0:.4f}".format(x_error / 2)) + trial_x
        calibrated = False
    else:
        new_x = trial_x

    if abs(y_error) >= 0.02:
        new_y = float("{0:.4f}".format(y_error + trial_y)) if runs < (max_runs / 2) else float("{0:.4f}".format(y_error / 2)) + trial_y
        calibrated = False
    else:
        new_y = trial_y

    if abs(z_error) >= 0.02:
        new_z = float("{0:.4f}".format(z_error + trial_z)) if runs < (max_runs / 2) else float("{0:.4f}".format(z_error / 2)) + trial_z
        calibrated = False
    else:
        new_z = trial_z

    # making sure I am sending the lowest adjustment value
    diff = 100
    for v in [new_x ,new_y, new_z]:
        if abs(v) < diff:
            diff = -v
    new_x += diff
    new_y += diff
    new_z += diff

    if calibrated:
        print ("Final values\nM666 X{0} Y{1} Z{2}".format(str(new_x),str(new_y),str(new_z)))
    else:
        set_M_values(port, new_x, new_y, new_z)

    return calibrated, new_x, new_y, new_z

def set_M_values(port, x, y, z):

    print ("Setting values M666 X{0} Y{1} Z{2}".format(str(x),str(y),str(z)))

    port.write(('M666 X{0} Y{1} Z{2}\n'.format(str(x), str(y), str(z))).encode())
    out = port.readline().decode()

def run_calibration(port, trial_x, trial_y, trial_z, max_runs, max_error, runs = 0):
    runs += 1

    if runs > max_runs:
        sys.exit("Too many calibration attempts")
    print('\nCalibration run {1} out of {0}'.format(str(max_runs), str(runs)))

    x_ave, y_ave, z_ave = get_current_values(port)

    x_error, y_error, z_error = determine_error(x_ave, y_ave, z_ave)

    if abs(max([x_error, y_error, z_error], key=abs)) > max_error and runs > 1:
        sys.exit("Calibration error on non-first run exceeds set limit")

    calibrated, new_x, new_y, new_z = calibrate(port, x_error, y_error, z_error, trial_x, trial_y, trial_z, max_runs, runs)

    if calibrated:
        print ("Calibration complete")
    else:
        calibrated, new_x, new_y, new_z = run_calibration(port, new_x, new_y, new_z, max_runs, max_error, runs)

    return calibrated, new_x, new_y, new_z

def main():
    # Default values
    max_runs = 14
    max_error = 1

    trial_x = 0.0
    trial_y = 0.0
    trial_z = 0.0
    l_value = 121.36
    r_value = 62.70
    step_mm = 57.14

    parser = argparse.ArgumentParser(description='Auto-Bed Cal. for Monoprice Mini Delta')
    parser.add_argument('-p','--port',help='Serial port',required=True)
    parser.add_argument('-r','--r-value',type=float,default=r_value,help='Starting r-value')
    parser.add_argument('-l','--l-value',type=float,default=l_value,help='Starting l-value')
    parser.add_argument('-s','--step-mm',type=float,default=step_mm,help='Set steps-/mm')
    parser.add_argument('-me','--max-error',type=float,default=max_error,help='Maximum acceptable calibration error on non-first run')
    parser.add_argument('-mr','--max-runs',type=int,default=max_runs,help='Maximum attempts to calibrate printer')
    parser.add_argument('-f','--file',type=str,dest='file',default=None,
        help='File with settings, will be updated with latest settings at the end of the run')
    args = parser.parse_args()

    port = establish_serial_connection(args.port)

    if args.file:
        try:
            with open(args.file) as data_file:
                settings = json.load(data_file)
            max_runs = int(settings.get('max_runs', max_runs))
            max_error = float(settings.get('max_error', max_error))
            trial_x = float(settings.get('x', trial_x))
            trial_y = float(settings.get('y', trial_y))
            trial_z = float(settings.get('z', trial_z))
            r_value = float(settings.get('r', r_value))
            l_value = float(settings.get('l', l_value))
            step_mm = float(settings.get('step', step_mm))

        except:
            max_error = args.max_error
            max_runs = args.max_runs
            r_value = args.r_value
            step_mm = args.step_mm
            max_runs = args.max_runs
            l_value = args.l_value
            pass

    if port:

        #Shouldn't need it once firmware bug is fixed
        #print ('Setting up M92 X{0} Y{0} Z{0}\n'.format(str(step_mm)))
        #port.write(('M92 X{0} Y{0} Z{0}\n'.format(str(step_mm))).encode())
        #out = port.readline().decode()

        print ('Setting up M665 L{0} R{1}\n'.format(str(l_value), str(r_value)))
        port.write(('M665 L{0} R{1}\n'.format(str(l_value), str(r_value))).encode())
        out = port.readline().decode()

        set_M_values(port, trial_x, trial_y, trial_z)

        print ('\nStarting calibration')

        calibrated, new_x, new_y, new_z = run_calibration(port, trial_x, trial_y, trial_z, max_runs, args.max_error)

        port.close()

        if calibrated and args.file:
            data = {'x':new_x, 'y':new_y, 'z':new_z, 'r':r_value, 'l': l_value, 'step':step_mm, 'max_runs':max_runs, 'max_error':max_error}
            with open(args.file, "w") as text_file:
                text_file.write(json.dumps(data))


if __name__ == '__main__':
    main()
