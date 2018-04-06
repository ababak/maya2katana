#!/usr/bin/python
'''
    maya2katana - Pixar Renderman plugin
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
    Copy shader nodes to Katana
    ------------------------------
'''

import re
import xml.etree.ElementTree as ET

import maya.cmds as cmds

from ... import utils

def preprocessNetworkMaterial(node):
    '''
    Preprocess shadingEngine node and remap correct attributes
    '''
    nodes = {}
    nodeName = node['name']
    connections = node['connections']
    newConnections = {}
    for i in ['surfaceShader', 'volumeShader']:
        connection = connections.get(i)
        if connection:
            newConnections['prmanBxdf'] = connection
            break
    displacementConnection = connections.get('displacementShader')
    if displacementConnection:
        newConnections['prmanDisplacement'] = displacementConnection
    nodes[nodeName] = node
    node['connections'] = newConnections
    return nodes


def postprocessNetworkMaterial(node, allNodes):
    '''
    Rename the networkMaterial node and connect bump
    '''
    nodes = {}
    prmanSurface = node['connections'].get('prmanBxdf')
    if prmanSurface:
        shaderNode = allNodes.get(prmanSurface['node'])
        if shaderNode:
            shaderNodeName = shaderNode['name']
            # Remove the output node to reinsert it back with the new name
            allNodes.pop(shaderNodeName, None)
            materialName = shaderNodeName
            shaderNodeName += '_out'
            shaderNode['name'] = shaderNodeName
            nodes[shaderNodeName] = shaderNode
            node['name'] = materialName
            node['renamings'] = {
                materialName: {'name': shaderNodeName},
            }
            nodes[materialName] = node
    return nodes


def processNetworkMaterial(xmlGroup, node):
    '''
    Process NetworkMaterial to remove extra input ports
    '''
    for i in ['prmanBxdf', 'prmanDisplacement']:
        if i not in node['connections']:
            parameter = xmlGroup.find(
                "./port[@name='{param}']".format(param=i))
            xmlGroup.remove(parameter)


def preprocessDisplacement(node):
    '''
    Remove the displacement node as there is no counterpart in Katana
    but levae the connections
    '''
    nodes = {}
    nodeName = node['name']
    node['weight'] = 20

    node['type'] = 'range'
    connection = node.get('connections').get('displacement', {})
    rename = connection.get('node')
    node['connections'] = {
        'input': {'node': rename, 'originalPort': utils.getOutConnection(connection)},
    }
    nodes[nodeName] = node
    return nodes


# Preprocess keywords:
# - preprocess
# - postprocess (postprocess at level 0)
# - type (override type)
premap = {
    'shadingEngine': {
        'type': 'networkMaterial',
        'preprocess': preprocessNetworkMaterial,
        'postprocess': postprocessNetworkMaterial,
    },
    'displacementShader': {
        'preprocess': preprocessDisplacement,
    },
}

# Mappings keywords:
# - customColor
# - customProcess
mappings = {
    'networkMaterial': {
        'customColor': (0.4, 0.35, 0.2),
        'customProcess': processNetworkMaterial,
    },
}
