#!/usr/bin/python
'''
    maya2katana
    Copyright (C) 2016-2019 Andriy Babak, Animagrad

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

    Author: Andriy Babak
    e-mail: ababak@gmail.com
    ------------------------------
    Common utility functions to be imported by plugins
    ------------------------------
'''

import re
import logging
import maya.cmds as cmds

log = logging.getLogger('clip')


def node_attributes(node):
    '''
    Get Maya node attributes
    '''
    attributes = cmds.listAttr(node)
    attr = {}
    attr['node_name'] = node
    attr['node_type'] = cmds.nodeType(node)
    for attribute in attributes:
        if '.' in attribute:
            continue
        try:
            val = cmds.getAttr(node + '.' + attribute)
        except RuntimeError:
            continue
        attr[attribute] = val
    return attr


def unique_name(name=None, reset=False):
    '''
    Create a unique node name by appending A-Z letters
    '''
    if not hasattr(unique_name, 'usedNames') or reset is True:
        unique_name.usedNames = []
    if isinstance(reset, list):
        unique_name.usedNames = list(reset)
    if name in unique_name.usedNames:
        if name[-1] > 'Z':
            name = name + 'A'
        while name in unique_name.usedNames:
            c = chr(ord(name[-1]) + 1)
            if c > 'Z':
                c = 'AA'
            name = name[:-1] + c
    unique_name.usedNames.append(name)
    return name


def get_out_connection(connection):
    '''
    Generate full connection path
    '''
    if not connection:
        return ''
    out_port = [strip_namespace(connection['node'])]
    if connection.get('original_port').startswith(
            ('outDisplacement', 'outEigenvalue')):
        out_port.append(connection.get('original_port'))
    elif connection.get('original_port').startswith('out'):
        out_port.append('out')
    else:
        out_port.append(connection.get('original_port'))
    original_port = re.findall(
        r'^out(?:Color|Value)([RGBAXYZ])',
        connection.get('original_port') or '')
    if original_port:
        out_port.append(original_port[0].lower())
    return '.'.join(out_port)


def rename_connections(nodes):
    '''
    Perform node renamings
    '''
    renamings = {}
    for node_name, node in nodes.items():
        renamings.update(node['renamings'])
    for node_name, node in nodes.items():
        for source in node['connections'].values():
            if source.get('node') not in renamings:
                continue
            renaming = renamings[source['node']]
            if node_name == renaming['name']:
                continue
            # print 'Renaming "{original}" to "{new}" ({port})'.format(
            #     original=source['node'],
            #     new=renaming['name'],
            #     port=renaming['original_port'])
            source['node'] = renaming['name']
            original_port = renaming.get('original_port')
            if original_port:
                source['original_port'] = original_port


def propagate_connection_weights(nodes):
    '''
    Connections may include weights so we need to propagate
    them to respective upstream nodes
    '''
    for node in nodes.values():
        for source in node['connections'].values():
            weight = source.get('weight')
            if not weight:
                continue
            target_node = nodes[source['node']]
            target_node['weight'] = target_node.get('weight', 0) + weight


def has_connection(node, param):
    '''
    Check if node dictionary includes the requested attribute connection
    '''
    return param in node['connections']


def strip_namespace(name):
    '''
    Strip all namespaces.
    Katana imports nodes with namespaces but at least RenderMan
    refuses to render them
    '''
    return name.rsplit(':', 1)[-1]
