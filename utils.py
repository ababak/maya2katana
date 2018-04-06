#!/usr/bin/python
'''
    maya2katana
    Copyright (C) 2016-2018 Andrey Babak, Animagrad

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    Author: Andrey Babak
    e-mail: ababak@gmail.com
    ------------------------------
    Common utility functions to be imported by plugins
    ------------------------------
'''

import re
import logging

import maya.cmds as cmds

log = logging.getLogger('clip')

def nodeAttributes(node):
    '''
    Get Maya node attributes
    '''
    attributes = cmds.listAttr(node)
    attr = {}
    attr['nodeName'] = node
    attr['nodeType'] = cmds.nodeType(node)
    for attribute in attributes:
        if '.' in attribute:
            continue
        try:
            val = cmds.getAttr(node + '.' + attribute)
        except RuntimeError:
            continue
        attr[attribute] = val
    return attr

def uniqueName(name=None, reset=False):
    '''
    Create a unique node name by appending A-Z letters
    '''
    if not hasattr(uniqueName, 'usedNames') or reset is True:
        uniqueName.usedNames = []
    if isinstance(reset, list):
        uniqueName.usedNames = list(reset)
    if name in uniqueName.usedNames:
        if name[-1] > 'Z':
            name = name + 'A'
        while name in uniqueName.usedNames:
            c = chr(ord(name[-1]) + 1)
            if c > 'Z':
                c = 'AA'
            name = name[:-1] + c
    uniqueName.usedNames.append(name)
    return name

def getOutConnection(connection):
    outPort = [connection['node'], 'out']
    originalPort = re.findall(
        r'^out(?:Color|Value)([RGBAXYZ])',
        connection.get('originalPort') or '')
    if originalPort:
        outPort.append(originalPort[0].lower())
    return '.'.join(outPort)

def renameConnections(nodes):
    renamings = {}
    for nodeName, node in nodes.items():
        renamings.update(node['renamings'])
    for nodeName, node in nodes.items():
        for source in node['connections'].values():
            if source['node'] not in renamings:
                continue
            renaming = renamings[source['node']]
            if nodeName == renaming['name']:
                continue
            # print 'Renaming "{original}" to "{new}" ({port})'.format(
            #     original=source['node'],
            #     new=renaming['name'],
            #     port=renaming['originalPort'])
            source['node'] = renaming['name']
            originalPort = renaming.get('originalPort')
            if originalPort:
                source['originalPort'] = originalPort

def hasConnection(node, param):
    return param in node['connections']
