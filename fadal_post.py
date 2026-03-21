# ***************************************************************************
# *   Copyright (c) 2014 sliptonic <shopinthewoods@gmail.com>               *
# *   Copyright (c) 2021 shadowbane1000 <tyler@colberts.us>                 *
# *   Copyright (c) 2023 Paul Gettings <p.gettings@gmail.com>               *
# *   Modified by Kyle Harris from https://www.terraflop.org/pydnc/         *
# *   fadal_post.py, get the latest version at: https://github.com/KCommits/*
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   Set to inch for default, adapted from fanuc posts for Fadal dialect   *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Lesser General Public License for more details.                   *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************
from __future__ import print_function

from distutils.command.build_scripts import first_line_re

import FreeCAD
from FreeCAD import Units
import Path
import argparse
import datetime
import shlex
import Path.Post.Utils as PostUtils

from PySide import QtGui

## TODO: Fadal 88HS appears to require Windows-style CRLF line endings. Fix this for other OS.

TOOLTIP = '''
This is a postprocessor file for the CAM workbench. It is used to
take a pseudo-gcode fragment outputted by a Path object, and output
real GCode suitable should be suitable for Fadal controllers (format 2).
This postprocessor, once placed in the appropriate PathScripts folder,
can be used directly from inside FreeCAD, via the GUI importer, or via
python scripts with:

import fadal_post
fadal_post.export(object,"/path/to/file.ncc","")
'''

now = datetime.datetime.now()

parser = argparse.ArgumentParser(prog='fadal', add_help=False)
parser.add_argument('--no-header', action='store_true', help='suppress header output')
parser.add_argument('--no-comments', action='store_true', help='suppress comment output')
parser.add_argument('--line-numbers', action='store_true', help='prefix with line numbers')
parser.add_argument('--no-show-editor', action='store_true', help='don\'t pop up editor before writing output')
parser.add_argument('--precision', default='3', help='number of digits of precision, default=3')
parser.add_argument('--inches', action='store_true', help='Convert output for US imperial mode (G20)')
parser.add_argument('--mm', action='store_true', help='Convert output for metric millimeters (G21)')
parser.add_argument('--no-modal', action='store_true', help='Don\'t output the Same G-command Name USE NonModal Mode')
parser.add_argument('--no-axis-modal', action='store_true', help='Don\'t output the Same Axis Value Mode')
parser.add_argument('--no-tlo', action='store_true', help='suppress tool length offset (G43) following tool changes')
parser.add_argument('--program-number', action='store_true', help='add program number to start of file')
parser.add_argument(
    "--preamble",
    help='set commands to be issued before the first command, default="G17\nG90"',
)
parser.add_argument(
    "--postamble",
    help='set commands to be issued after the last command, default="M05\nG17 G90\nM2"',
)

TOOLTIP_ARGS = parser.format_help()

# These globals set common customization preferences
OUTPUT_COMMENTS = True
OUTPUT_HEADER = True
OUTPUT_LINE_NUMBERS = False
SHOW_EDITOR = True
MODAL = True  # if true commands are suppressed if the same as previous line.
USE_TLO = True # if true G43 will be output following tool changes
OUTPUT_DOUBLES = False  # if false duplicate axis values are suppressed if the same as previous line.
COMMAND_SPACE = " "
LINENR = 100  # line number starting value
LINEDELTA = 5 # line number increment
OUTPUT_PROGNR = True # add Oxxxx to head of program
TLC = False # flag for output of G43 Hxx on Z move
# Adding a CURRENT_TOOL variable to keep track of the current tool number.
CURRENT_TOOL = 0
# Store the current fixture offset tag (e.g., E1, G54, etc.) to insert after tool change
PENDING_FIXTURE_OFFSET = ""

# These globals will be reflected in the Machine configuration of the project
UNITS = "G20"  # G21 for metric, G20 for us standard
UNIT_SPEED_FORMAT = 'in/min'
UNIT_FORMAT = 'in'
PRECISION = 3

MACHINE_NAME = "fadal"
# Fadal machine has machine home in center of travel, except Z!
# Z machine 0 at tool change location, 4 in below max travel up.
CORNER_MIN = {'x': -10, 'y': -8, 'z': -16}
CORNER_MAX = {'x': 10, 'y': 8, 'z': 4}

# Preamble text will appear at the beginning of the GCODE output file.
PREAMBLE = '''G17 G40 G49 G80 G90
'''

# Postamble text will appear following the last operation.
POSTAMBLE = '''M05
G28 G91 Z0.
G90
G0
G53 X0. Y0.
M30
'''

# Pre operation text will be inserted before every operation
PRE_OPERATION = ''''''

# Post operation text will be inserted after every operation
POST_OPERATION = ''''''

# Tool Change commands will be inserted before a tool change
TOOL_CHANGE = '''M5
G0
G53 Z0
'''

# to distinguish python built-in open function from the one declared below
if open.__module__ in ['__builtin__','io']:
    pythonopen = open


def processArguments(argstring):
    # pylint: disable=global-statement
    global OUTPUT_HEADER
    global OUTPUT_COMMENTS
    global OUTPUT_LINE_NUMBERS
    global SHOW_EDITOR
    global PRECISION
    global PREAMBLE
    global POSTAMBLE
    global UNITS
    global UNIT_SPEED_FORMAT
    global UNIT_FORMAT
    global MODAL
    global USE_TLO
    global OUTPUT_PROGNR
    global OUTPUT_DOUBLES

    try:
        args = parser.parse_args(shlex.split(argstring))
        if args.no_header:
            OUTPUT_HEADER = False
        if args.no_comments:
            OUTPUT_COMMENTS = False
        if args.line_numbers:
            OUTPUT_LINE_NUMBERS = True
        if args.no_show_editor:
            SHOW_EDITOR = False
        print("Show editor = %d" % SHOW_EDITOR)
        PRECISION = args.precision
        if args.preamble is not None:
            PREAMBLE = args.preamble
        if args.postamble is not None:
            POSTAMBLE = args.postamble
        if args.inches:
            UNITS = 'G20'
            UNIT_SPEED_FORMAT = 'in/min'
            UNIT_FORMAT = 'in'
            PRECISION = 4
        if args.mm:
            UNITS = 'G21'
            UNIT_SPEED_FORMAT = 'mm/min'
            UNIT_FORMAT = 'mm'
            PRECISION = 3
        if args.no_modal:
            MODAL = False
        if args.no_tlo:
            USE_TLO = False
        if args.no_axis_modal:
            OUTPUT_DOUBLES = True
        if args.program_number:
            OUTPUT_PROGNR = True

    except Exception as e:
        print(f"Exception During processArguments. Type: {type(e)} Error: {e}")
        return False

    return True


def export(objects_list, filename, argstring):
    print("fadal_post.export() Started")
    if not processArguments(argstring):
        return None
    global UNITS
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT
    global USE_TLO
    global OUTPUT_PROGNR
    global TLC
    global OUTPUT_HEADER
    global MIST

    for obj in objects_list:
        if not hasattr(obj, "Path"):
            print("the object " + obj.Name + " is not a path. Please select only path and Compounds.")
            return None

    print("Postprocessing...")
    gcode = "%\n" # need % at the beginning of file for Fadal upload

    # Output a program number
    # Format for nc-file *_xxxx.nc2 whereby xxxx=program number
    if OUTPUT_PROGNR == True:
        reply = QtGui.QInputDialog.getText(None,"FadalPost","Enter program number")
        print(f"Reply from OUTPUT_PROGNR: {reply}")
        if reply[1]:
            gcode += f"O{reply[0]}\n"

    print(f"Write the header.")
    if OUTPUT_HEADER:
        # gcode += f"{os.path.split(filename)[-1]}\n"
        gcode += f"{line_number()}(Post Processor: {__name__.upper()})\n"
        gcode += f"{line_number()}(Process time: {str(now).upper()})\n"

    print(f"Write the preamble.")
    if OUTPUT_COMMENTS:
        gcode += f"{line_number()}(Begin Preamble)\n"
    for line in PREAMBLE.splitlines(False):
        gcode += f"{line_number()}{line}\n"

    # Add units G-code
    gcode += f"{line_number()}{UNITS}\n"

    print(f"Iterating over the objectslist.")
    for obj in objects_list:

        # Skip inactive operations
        if hasattr(obj, 'Active'):
            if not obj.Active:
                continue
        if hasattr(obj, 'Base') and hasattr(obj.Base, 'Active'):
            if not obj.Base.Active:
                continue

        # Add pre-op comments
        if OUTPUT_COMMENTS:
            gcode += f"{line_number()}(BEGIN OPERATION: {obj.Label.upper()})\n"
            # gcode += f"{line_number()}(MACHINE UNITS: {UNIT_SPEED_FORMAT.upper()})\n"
        for line in PRE_OPERATION.splitlines(True):
            gcode += f"{line_number()}{line}"

        # Get coolant mode
        coolant_mode = 'None'
        if hasattr(obj, "CoolantMode") or hasattr(obj, 'Base') and  hasattr(obj.Base, "CoolantMode"):
            if hasattr(obj, "CoolantMode"):
                coolant_mode = obj.CoolantMode
            else:
                coolant_mode = obj.Base.CoolantMode

        # Turn coolant on if required
        if OUTPUT_COMMENTS:
            if not coolant_mode == 'None':
                gcode += f"{line_number()}(COOLANT ON:{coolant_mode.upper()})\n"
        if coolant_mode == 'Flood':
            gcode += f"{line_number()}M8\n"
        if coolant_mode == 'Mist':
            # This mill uses the air brake for mist coolant!
            gcode += f"{line_number()}M60\n"
            
        # Process the operation gcode
        gcode += parse(obj)

        # Do the post_op
        if OUTPUT_COMMENTS:
            gcode += f"{line_number()}(FINISH OPERATION: {obj.Label.upper()})\n"
        for line in POST_OPERATION.splitlines(True):
            gcode += f"{line_number()}{line}"

        # Turn coolant off if required
        if not coolant_mode == 'None':
            if OUTPUT_COMMENTS:
                gcode += f"{line_number()}(COOLANT OFF: {coolant_mode.upper()})\n"
            gcode += f"{line_number()}M9\n"
            if coolant_mode == 'Flood':
                gcode += f"{line_number()}M9\n"
            if coolant_mode == 'Mist':
                # This mill uses the air brake for mist coolant!
                gcode += f"{line_number()}M61\n"

    # Do the postamble
    if OUTPUT_COMMENTS:
        gcode += f"(BEGIN POSTAMBLE)\n"
    for line in POSTAMBLE.splitlines(True):
        gcode += f"{line_number()}{line}"
    gcode += "%\n"

    if FreeCAD.GuiUp and SHOW_EDITOR:
        dia = PostUtils.GCodeEditorDialog()
        dia.editor.setText(gcode)
        result = dia.exec_()
        if result:
            final = dia.editor.toPlainText()
        else:
            final = gcode
    else:
        final = gcode

    print("Done postprocessing.")

    if not filename == '-':
        gfile = pythonopen(filename, "w")
        gfile.write(final)
        gfile.close()

    return final


def line_number():
    # pylint: disable=global-statement
    global LINENR
    if OUTPUT_LINE_NUMBERS is True:
        LINENR += LINEDELTA
        return f'N{str(LINENR)} '
    return ""


def parse(pathobj):
    # pylint: disable=global-statement
    global PRECISION
    global MODAL
    global OUTPUT_DOUBLES
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT
    global TLC
    global CURRENT_TOOL
    global PENDING_FIXTURE_OFFSET

    gcode_output_line_str = ""
    last_command = None
    precision_string = f".{PRECISION}f"
    curr_location = {}  # keep track for no doubles
    print(f"parse() startup! TLC is: {TLC}")
    # print(f"str of pathobj is {pathobj}")

    # The order of parameters
    params = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K', 'F', 'S', 'T', 'Q', 'R', 'L', 'H', 'D', 'P']
    first_move = Path.Command("G0", {"X": -1, "Y": -1, "Z": -1, "F": 0.0})
    curr_location.update(first_move.Parameters)  # set First location Parameters

    if hasattr(pathobj, "Group"):  # We have a compound or project.
        # if OUTPUT_COMMENTS:
        #     gcode_output_line_str += f"{line_number()}(compound: {pathobj.Label})\n"
        for p in pathobj.Group:
            gcode_output_line_str += parse(p)
        return gcode_output_line_str
    else:  # parsing simple path
        # groups might contain non-path things like stock.
        if not hasattr(pathobj, "Path"):
            return gcode_output_line_str

        # if OUTPUT_COMMENTS:
        #     gcode_output_line_str += f"{line_number()}({pathobj.Label})\n"

        for index, c in enumerate(pathobj.Path.Commands):
            gcode_word_list = []
            command = c.Name
            if index + 1 == len(pathobj.Path.Commands):
              next_command = ""
            else:
              next_command = pathobj.Path.Commands[index+1].Name

            # adaptive_op not defined in pyDNC version, adding below definitions similar to fanuc post
            adaptive_op = False
            op_horiz_rapid = 0
            op_vert_rapid = 0

            if adaptive_op and c.Name in ["G0", "G00"]:
                if op_horiz_rapid and op_vert_rapid:
                    command = 'G1'
                else:
                    gcode_word_list.append('(TOOL CONTROLLER RAPID VALUES ARE UNSET)\n')

            # Handle the "Fixture" operation, which outputs the fixture offset (e.g. E1/G54)
            if pathobj.Label == "Fixture":
                # Suppress moves in fixture selection
                if command == "G0":
                    continue
                # Capture fixture offset commands (e.g., E1, G54, G55, etc.) and store for later
                if command not in ["G0", "G00"] and not command.startswith("("):
                    PENDING_FIXTURE_OFFSET = command
                    # Skip outputting the fixture offset here; it will be added after tool change
                    last_command = command
                    continue

            # TODO: Drill cycles do not work with pyDNC version of this post and FreeCAD v1.0.2, the attribs checked
            #  in that version dont exist. I'm attempting a rewrite but havent tested it with tapping at all. I have
            #  only tested it with peck drill cycles.
            is_tap = False
            # Evaluate whether the tool is a tap.
            if hasattr(pathobj, 'ToolController') and hasattr(pathobj.ToolController, 'Tool'):
                tool = pathobj.ToolController.Tool
                if hasattr(tool, 'ToolType'):
                    is_tap = tool.ToolType == "Tap"
                elif hasattr(tool, 'ShapeName'):
                    is_tap = tool.ShapeName == "tap"
                elif hasattr(tool, 'BitShape'):
                    is_tap = "tap" in tool.BitShape.lower()
            # Do the conversion for tapping if needed.
            if (command == "G81" or command == "G83") and is_tap:
                gcode_word_list.append("G84 G99")
                # append additional parameters for tapping
                if "R" in c.Parameters:
                    gcode_word_list.append(f"R0{Units.Quantity(c.Parameters['R'], FreeCAD.Units.Length)}")
                else:
                    gcode_word_list.append(f"R0{Units.Quantity(curr_location['Z'], FreeCAD.Units.Length)}")
                    # c.Parameters.del("R")
                if "S" in c.Parameters:
                    gcode_word_list.append(f"F{int(c.Parameters['S'])}")
                    # c.Parameters.del("S")
            else: # Otherwise, add command to output
                gcode_word_list.append(command)
            ### End untested tapping code ###

            # if modal: suppress the command if it is the same as the last one
            if MODAL is True:
                if command == last_command:
                    gcode_word_list.pop(0)

            # suppress a G80 between two identical command
            if command == "G80" and last_command == next_command:
                continue

            if command[0] == '(' and not OUTPUT_COMMENTS: # command is a comment
                continue

            # Now add the remaining parameters in order
            for param in params:
                if param in c.Parameters:
                    # print(f"Current param in c.Parameters: {param}")
                    if param == 'F' and (curr_location[param] != c.Parameters[param] or OUTPUT_DOUBLES):
                        if command not in ["G0", "G00"]:  # fadal doesn't use rapid speeds
                            speed = Units.Quantity(c.Parameters['F'], FreeCAD.Units.Velocity)
                            if speed.getValueAs(UNIT_SPEED_FORMAT) > 0.0:
                                gcode_word_list.append(
                                    f"{param}{float(speed.getValueAs(UNIT_SPEED_FORMAT)):{precision_string}}")
                            else:
                                continue
                    elif param == 'T':
                        gcode_word_list.append(f"{param}{int(c.Parameters['T'])}")
                        CURRENT_TOOL = int(c.Parameters['T'])
                    elif param == 'H':
                        gcode_word_list.append(f"{param}{int(c.Parameters['H'])}")
                    elif param == 'D':
                        gcode_word_list.append(f"{param}{int(c.Parameters['D'])}")
                    elif param == 'S':
                        gcode_word_list.append(f"{param}{int(c.Parameters['S'])}")
                    else: # Coordinates & other parameters
                        if param == 'Z' and TLC: # add G43 Hxx to first Z move
                          # The post from pyDNC added the G43 HXX to the first Z move which resulted in an unintended overtravel of Z.
                          # If there's a pending fixture offset, insert a G0 line with it before the G43 line
                          if PENDING_FIXTURE_OFFSET:
                              gcode_output_line_str += f"{line_number()}G0 {PENDING_FIXTURE_OFFSET}\n"
                              PENDING_FIXTURE_OFFSET = ""
                          pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                          gcode_word_list.append(
                              f"G43 {param}{float(pos.getValueAs(UNIT_FORMAT)):{precision_string}} H{CURRENT_TOOL}")
                          TLC = False
                        elif (not OUTPUT_DOUBLES) and (param in curr_location) and (curr_location[param] == c.Parameters[param]):
                            continue
                        else:
                            pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                            gcode_word_list.append(f"{param}{float(pos.getValueAs(UNIT_FORMAT)):{precision_string}}")

            # store the latest command
            last_command = command
            curr_location.update(c.Parameters)

            # Check for Tool Change:
            if command == 'M6':
                # add tool change preamble
                for line in TOOL_CHANGE.splitlines(True):
                    gcode_output_line_str += line_number() + line
                # flag for adding height offset to next Z move
                TLC = True

            if command == "message":
                if OUTPUT_COMMENTS is False:
                    gcode_output_line_str = []
                else:
                    gcode_word_list.pop(0)  # remove the command

            # Prepend a line number and append a newline
            if len(gcode_word_list) >= 1:
                if OUTPUT_LINE_NUMBERS:
                    gcode_word_list.insert(0, (line_number()))

                # append the line to the final output
                for word in gcode_word_list:
                    gcode_output_line_str += word.upper() + COMMAND_SPACE
                gcode_output_line_str = gcode_output_line_str.strip() + "\n"

        return gcode_output_line_str

# print(__name__ + " gcode postprocessor loaded.")
