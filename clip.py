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
    Copy shader nodes to Katana
    ------------------------------
'''

import os
import traceback
import xml.etree.ElementTree as ET

import maya.cmds as cmds

from . import utils

try:
    import PySide
    clipboard = PySide.QtGui.QApplication.clipboard()
except ImportError:
    import PySide2
    clipboard = PySide2.QtGui.QGuiApplication.clipboard()

basedir = os.path.dirname(os.path.realpath(__file__))

KATANA_NODE_WIDTH = 200
KATANA_SPACE_WIDTH = 60
KATANA_ROW_HEIGHT = 100

def equalAttributes(a, b):
    '''
    Compare two attributes for equality
    '''
    delta = 0.001
    if isinstance(a, (list, tuple)):
        for val_a, val_b in zip(a, b):
            if not equalAttributes(val_a, val_b):
                return False
        return True
    elif isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < delta
    elif isinstance(a, bool) or isinstance(b, bool):
        if not isinstance(a, bool):
            a = (a == 'True') or int(a) == 1
        if not isinstance(b, bool):
            b = (b == 'True') or int(b) == 1
        return a == b
    elif isinstance(a, int) or isinstance(b, int):
        return int(a) == int(b)
    else:
        return a == b

def iterateMappingRecursive(mappingDict, xmlGroup, node):
    '''
    The most complicated part that maps Maya parameters to Katana XML parameters
    '''
    attributes = node['attributes']
    for paramKey, paramChildren in mappingDict.items():
        options = None
        processField = None
        forceContinue = False
        destKey = paramKey
        # Special case: custom processing (used for ramp, etc.)
        if paramKey == 'customProcess':
            processField = paramChildren
            processField(xmlGroup, node)
            continue
        elif paramKey == 'customColor':
            xmlGroup.attrib['ns_colorr'] = str(paramChildren[0])
            xmlGroup.attrib['ns_colorg'] = str(paramChildren[1])
            xmlGroup.attrib['ns_colorb'] = str(paramChildren[2])
            continue
        if isinstance(paramChildren, tuple):
            destKey = paramChildren[0]
            paramChildren = paramChildren[1]
        if isinstance(paramChildren, list):
            options = paramChildren
            paramChildren = None
        if isinstance(paramChildren, str):
            destKey = paramChildren
            paramChildren = None
            for connectionName, connection in node['connections'].items():
                if connectionName == paramKey:
                    node['connections'][destKey] = connection
                    del node['connections'][connectionName]
        if callable(paramChildren):
            processField = paramChildren
            paramChildren = None
        parameter = xmlGroup.find(
            ".//group_parameter[@name='parameters']"
            "//group_parameter[@name='{param}']".format(param=destKey))
        # print paramKey, destKey, node
        if parameter is not None:
            enableNode = parameter.find("*[@name='enable']")
            typeNode = parameter.find("string_parameter[@name='type']")
            # print parameter, enableNode, typeNode
            parameterType = ''
            if typeNode is not None:
                parameterType = typeNode.get('value')
            valueNode = parameter.find("*[@name='value']")
            tuples = None
            if valueNode is not None:
                value = valueNode.get('value')
                # print(paramKey, value)
                if not value:
                    tuples = valueNode.get('size')
                    if tuples:
                        value = ()
                        for i in range(int(tuples)):
                            subValue = valueNode.find(
                                "*[@name='i{index}']".format(index=i)).get('value')
                            if parameterType == 'FloatAttr':
                                subValue = float(subValue)
                            elif parameterType == 'IntAttr':
                                subValue = int(subValue)
                            value += (subValue,)
                mayaValue = attributes.get(paramKey)
                if isinstance(mayaValue, list) and len(mayaValue) == 1:
                    mayaValue = mayaValue[0]
                if utils.hasConnection(node, destKey):
                    mayaValue = value
                    forceContinue = True
                # if isinstance(mayaValue, dict):
                #   source = mayaValue['source']
                #   portNode = xmlGroup.find(".//port[@name='{param}']".format(param=destKey))
                #   if portNode is not None:
                #       portNode.attrib['source'] = source
                #   mayaValue = value
                #   forceContinue = True
                if options:
                    if mayaValue is not None:
                        mayaValue = options[mayaValue]
                if processField:
                    mayaValue = processField(paramKey, mayaValue)
                if mayaValue is not None and not equalAttributes(mayaValue, value):
                    # print(paramKey + ' = ' + str(value))
                    # print('\tnew value = ' + str(mayaValue))
                    if tuples:
                        for i, val in enumerate(mayaValue):
                            subValueNode = valueNode.find("*[@name='i{index}']".format(index=i))
                            subValueNode.attrib['value'] = str(val)
                    else:
                        if isinstance(mayaValue, bool):
                            mayaValue = int(mayaValue)
                        # print('\tnew value = ' + str(mayaValue))
                        valueNode.attrib['value'] = str(mayaValue)
                    if enableNode is not None:
                        enableNode.attrib['value'] = '1'
                else:
                    # print('Default value found for "{key}": {value}'.format(
                    #     key=paramKey,
                    #     value=value))
                    pass
                if mayaValue == 0 and not forceContinue:
                    # No need to continue processing
                    paramChildren = None
        if paramChildren:
            # if paramChildren is not None
            iterateMappingRecursive(paramChildren, xmlGroup, node)

def preprocessNode(nodeName, premap):
    '''
    Preprocessing a node.
    This is needed as some nodes (like ramp or bump) can be
    replaced by several other nodes for Katana.
    We return either one original node or several
    nodes if something was replaced during preprocessing
    '''
    nodeType = cmds.nodeType(nodeName)
    if nodeType not in premap:
        return None
    nodes = {}
    attributes = utils.nodeAttributes(nodeName)
    connections = {}
    nodeConnections = cmds.listConnections(
        nodeName,
        source=True,
        destination=False,
        connections=True,
        plugs=True)
    if nodeConnections:
        for i in range(len(nodeConnections) / 2):
            connTo = nodeConnections[i * 2]
            connTo = connTo[connTo.find('.') + 1:]
            connFrom = nodeConnections[i * 2 + 1]
            connections[connTo] = {
                'node': connFrom[:connFrom.find('.')],
                'originalPort': connFrom[connFrom.find('.') + 1:]
            }

    node = {
        'name': nodeName,
        'type': nodeType,
        'attributes': attributes,
        'connections': connections,
        'renamings': {}
    }
    premapSettings = premap[nodeType]
    for attr in ['type', 'postprocess']:
        if premapSettings.get(attr):
            node[attr] = premapSettings.get(attr)
    if premapSettings.get('preprocess'):
        preprocessFunc = premapSettings.get('preprocess')
        if preprocessFunc:
            preprocessResult = preprocessFunc(node)
            if preprocessResult:
                nodes.update(preprocessResult)
    else:
        nodes[node['name']] = node
    return nodes

def processNode(node, renderer, mappings):
    '''
    Start individual node processing
    '''
    if 'name' not in node:
        return None
    nodeName = node['name']
    nodeType = node['type']
    if nodeType not in mappings:
        return None
    xmlPath = os.path.join(basedir, 'renderer', renderer, 'nodes', nodeType + '.xml')
    if not os.path.isfile(xmlPath) or mappings.get(nodeType) is None:
        return None
    tree = ET.parse(xmlPath)
    root = tree.getroot()
    root.attrib['name'] = nodeName
    xmlNode = root.find("./group_parameter/string_parameter[@name='name']")
    if xmlNode is not None:
        xmlNode.attrib['value'] = nodeName
    iterateMappingRecursive(mappings[nodeType], root, node)
    return root

def isConnected(source, dest):
    '''
    Test if given nodes have common connections
    '''
    connections = dest.get('connections')
    if connections:
        for connection in connections.values():
            if source['name'] == connection['node']:
                return True
    return False

def checkOrphanedNodes(tree, nodes, node):
    '''
    Check for orphaned nodes at root level
    '''
    # print('Checking ' + node['name'])
    if nodes[node['name']].get('weight'):
        node['weight'] = nodes[node['name']].get('weight')
    removeList = []
    for leaf in tree['children']:
        # leafNode = leaf['name']
        # print('-- Testing against ' + leafNode)
        if isConnected(leaf, nodes[node['name']]):
            # print('   Reordering...')
            # print('   Before:' + str(tree))
            removeList.append(leaf)
            node['children'].append(leaf)
            # print('   After:' + str(tree))
    for leaf in removeList:
        tree['children'].remove(leaf)

def insertNode(tree, nodes, branch, node, level=0):
    '''
    Main processing starts here. The nodes are inserted one by one.
    We build a tree by finding a correct place for each new node dynamically
    Orphaned nodes are inserted at root level
    '''
    leafNode = branch['name']
    if leafNode in nodes:
        if isConnected(node, nodes[leafNode]):
            # We have found the right place to add a child
            checkOrphanedNodes(tree, nodes, node)
            branch['children'].append(node)
            return True
    if branch['children']:
        for leaf in branch['children']:
            if insertNode(tree, nodes, leaf, node, level + 1):
                return True
    if level > 0:
        return False
    # insert at level 0 (root child)
    checkOrphanedNodes(tree, nodes, node)
    # print('++ Inserting ' + node['name'])
    branch['children'].append(node)
    return True

def buildTree(nodes):
    '''
    Build a tree from plain list of nodes
    '''
    tree = {'name': 'root', 'children': []}
    for node in nodes.values():
        if 'name' in node:
            insertNode(tree, nodes, tree, {'name': node['name'], 'children': []})
    calcTreeWidth(tree)
    calcTreePos(tree)
    return tree

def exportTree(branch, nodesXml, level=0):
    '''
    Recursively build XML
    '''
    result = []
    if branch['name'] in nodesXml:
        nodesXml[branch['name']].attrib['x'] = str(branch['x'])
        nodesXml[branch['name']].attrib['y'] = str(KATANA_ROW_HEIGHT * level)
        result.append(nodesXml[branch['name']])
    if branch['children']:
        for leaf in branch['children']:
            result += exportTree(leaf, nodesXml, level + 1)
    return result

def printTree(branch, level=0):
    '''
    Debug routine to print the resulting tree
    '''
    if branch['name']:
        print '  ' * level + branch['name']
    if branch['children']:
        for leaf in branch['children']:
            printTree(leaf, level + 1)

def calcTreeWidth(branch):
    '''
    Recursively update branches with their widths
    '''
    width = 0
    count = 0
    if branch['children']:
        for leaf in branch['children']:
            width += calcTreeWidth(leaf)
            count += 1
        width += (count - 1) * KATANA_SPACE_WIDTH
        branch['width'] = width
    else:
        width = KATANA_NODE_WIDTH
        branch['width'] = width
    return width

def calcTreePos(branch, x=0):
    '''
    Recursively update nodes with their positions
    '''
    branch['x'] = x
    if branch['children']:
        pos = x - branch['width'] / 2
        sortedBranch = sorted(branch['children'], key=lambda x: x.get('weight', 0))
        for leaf in sortedBranch:
            calcTreePos(leaf, pos + leaf['width'] / 2)
            pos += leaf['width'] + KATANA_SPACE_WIDTH

def connectXml(nodeXml, dest, source):
    # print dest + ' ' + str(source)
    portNode = nodeXml.find(".//port[@name='{param}']".format(param=dest))
    if portNode is not None:
        portNode.attrib['source'] = utils.getOutConnection(source)

def getAllShadingNodes(nodes):
    if not isinstance(nodes, list):
        nodes = [nodes]
    resultNodes = []
    while nodes:
        resultNodes += nodes
        nodes = cmds.listConnections(nodes, source=True, destination=False)
    return resultNodes

def establishConnections(nodes, nodesXml):
    for nodeName, nodeXml in nodesXml.items():
        for dest, source in nodes[nodeName]['connections'].items():
            connectXml(nodeXml, dest, source)

def generateXML(nodeNames, renderer=None):
    if not isinstance(nodeNames, list):
        nodeNames = [nodeNames]
    # Let's prepare the katana frame to enclose our nodes
    xmlRoot = ET.Element('katana')
    xmlRoot.attrib['release'] = '2.5v4'
    xmlRoot.attrib['version'] = '2.5.1.000001'
    xmlExportedNodes = ET.SubElement(xmlRoot, 'node')
    xmlExportedNodes.attrib['name'] = '__SAVE_exportedNodes'
    xmlExportedNodes.attrib['type'] = 'Group'
    # Collect the whole network if shadingEngine node is selected alone
    if len(nodeNames) == 1 and cmds.nodeType(nodeNames[0]) == 'shadingEngine':
        shadingGroup = nodeNames[0]
        nodeNames = []
        surface_shader = ''
        if cmds.attributeQuery('aiSurfaceShader', node=shadingGroup, exists=True):
            surface_shader = cmds.listConnections(shadingGroup + '.aiSurfaceShader')
        if not surface_shader:
            surface_shader = cmds.listConnections(shadingGroup + '.surfaceShader')
        if surface_shader:
            nodeNames += surface_shader
        volume_shader = ''
        if cmds.attributeQuery('aiVolumeShader', node=shadingGroup, exists=True):
            volume_shader = cmds.listConnections(shadingGroup + '.aiVolumeShader')
        if not volume_shader:
            volume_shader = cmds.listConnections(shadingGroup + '.volumeShader')
        if volume_shader:
            nodeNames += volume_shader
        if not renderer:
            shader = surface_shader or volume_shader
            shader_type = cmds.nodeType(shader)
            if shader_type.startswith('Pxr'):
                renderer = 'prman'
            elif shader_type.startswith(('ai', 'al')):
                renderer = 'arnold'
        displacement_shader = cmds.listConnections(shadingGroup + '.displacementShader')
        if displacement_shader:
            nodeNames += displacement_shader
        nodeNames = getAllShadingNodes(nodeNames)
        nodeNames.append(shadingGroup)
    if not renderer:
        utils.log.error('No renderer specified')
        return ''
    # Now we try to import renderer plugin
    try:
        renderer_package = __import__(
            'renderer.' + renderer,
            globals(),
            locals(),
            [],
            -1
        )
        renderer_module = getattr(renderer_package, renderer)
        reload(renderer_module)
    except Exception as e:
        utils.log.error('Error loading "{renderer}" renderer: {exc}'.format(
            renderer=renderer,
            exc=traceback.format_exc()))
        return ''
    # Collect the list of used node names to get unique names
    nodeNames = list(set(nodeNames))
    utils.uniqueName(reset=nodeNames)
    preprocessedNodes = {}
    for nodeName in nodeNames:
        preprocessedNode = preprocessNode(nodeName, premap=renderer_module.premap)
        if preprocessedNode:
            preprocessedNodes.update(preprocessedNode)
    utils.renameConnections(preprocessedNodes)
    graphTree = buildTree(preprocessedNodes)
    shouldUpdateTree = False
    for branch in graphTree['children']:
        nodeName = branch['name']
        node = preprocessedNodes[nodeName]
        if node.get('postprocess'):
            # Remove the affected node and reinsert its postprocessed replacement
            preprocessedNodes.pop(nodeName, None)
            postprocessFunc = node['postprocess']
            postprocessedNode = postprocessFunc(node, preprocessedNodes)
            preprocessedNodes.update(postprocessedNode)
            shouldUpdateTree = True
    if shouldUpdateTree:
        utils.renameConnections(preprocessedNodes)
        graphTree = buildTree(preprocessedNodes)
    nodesXml = {}
    for nodeName, node in preprocessedNodes.items():
        nodeXml = processNode(node, renderer=renderer, mappings=renderer_module.mappings)
        if nodeXml is not None:
            nodesXml[nodeName] = nodeXml
    establishConnections(preprocessedNodes, nodesXml)
    allXmlNodes = exportTree(graphTree, nodesXml)
    for xmlNode in allXmlNodes:
        xmlExportedNodes.append(xmlNode)
    if nodesXml:
        return ET.tostring(xmlRoot)
    return ''

def copy():
    '''
    Main node copy routine, called from shelf/menu
    Usage: Select the shading nodes to copy and call clip.copy()
    Then paste to Katana
    '''
    nodeNames = cmds.ls(selection=True)
    xml = generateXML(nodeNames)
    if xml:
        clipboard.setText(xml)
        utils.log.info('Successfully copied nodes to clipboard. You can paste them to Katana now.')
    else:
        utils.log.info('Nothing copied, sorry')
