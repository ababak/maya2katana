#!/usr/bin/python
'''
    maya2katana - RenderMan plugin
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
import re
import xml.etree.ElementTree as ET

import maya.cmds as cmds

from ... import utils

def replaceTex(key, filepath):
    '''
    Replace all texture paths with their .tex counterparts
    '''
    root, ext = os.path.splitext(filepath)
    if ext:
        ext = '.tex'
    root = root.replace('\\', '/')
    return root + ext


def preprocessUtilityPattern(node):
    '''
    Preprocess Utility Pattern surface connections
    '''
    nodes = {}
    nodeName = node['name']
    connections = node['connections']
    utilityPatterns = {}
    for i in connections:
        utilityMatch = re.search(r'^utilityPattern\[(\d+)\]$', i)
        if not utilityMatch:
            continue
        utilityPatterns[int(utilityMatch.group(1))] = connections.get(i)
    nodes[nodeName] = node
    if len(utilityPatterns) == 1:
        connections['utilityPattern'] = utilityPatterns.values()[0]
        del connections[
            'utilityPattern[{}]'.format(utilityPatterns.keys()[0])]
    elif len(utilityPatterns) > 1:
        # We should create a ShadingNodeArrayConnector
        connectorName = utils.uniqueName(nodeName + 'Connector')
        arrayConnections = {}
        for i in sorted(utilityPatterns):
            arrayConnections['i' + str(i)] = utilityPatterns.get(i)
            del connections[
                'utilityPattern[{}]'.format(i)]
        connector = {
            'name': connectorName,
            'type': 'ShadingNodeArrayConnector',
            'attributes': {},
            'connections': arrayConnections,
            'renamings': {},
        }
        connections['utilityPattern'] = {
            'node': connectorName,
            'originalPort': 'out',
        }
        nodes[connectorName] = connector
    return nodes

def processUtilityPattern(xmlGroup, node):
    '''
    Process Utility Pattern surface connections
    '''
    connections = node['connections']
    for i in sorted(connections):
        inPort = ET.SubElement(xmlGroup, 'port')
        inPort.attrib['name'] = i
        inPort.attrib['type'] = 'in'

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
    for i in [
            'prmanBxdf',
            'prmanDisplacement',
            'prmanDisplayfilter',
            'prmanIntegrator',
            'prmanLight',
            'prmanLightfilter',
            'prmanPattern',
            'prmanProjection',
            'prmanSamplefilter',
            'prmanCoshaders.coshader',
        ]:
        if i not in node['connections']:
            parameter = xmlGroup.find(
                "./port[@name='{param}']".format(param=i))
            xmlGroup.remove(parameter)


def preprocessDisplacement(node):
    '''
    Change the weight to move the displacement subtree to the right
    '''
    nodes = {}
    nodeName = node['name']
    node['weight'] = 20
    nodes[nodeName] = node
    return nodes


def processRamp(xmlGroup, node):
    '''
    Process PxrRamp
    '''
    attributes = node['attributes']
    nodeName = node['name']
    if not nodeName:
        return
    nodeType = node['type']
    if not nodeType:
        return
    colorEntryListSize = cmds.getAttr(
        '{node}.positions'.format(node=nodeName), size=True)
    colorEntryList = []
    hasConnections = False
    colorEntryListIndices = sorted(cmds.getAttr(
        '{node}.positions'.format(node=nodeName), multiIndices=True))
    index = 0
    for i in colorEntryListIndices:
        valuePosition = cmds.getAttr('{node}.positions[{index}]'.format(
            node=nodeName, index=i))
        valueColor = cmds.getAttr('{node}.colors[{index}]'.format(
            node=nodeName, index=i))
        valueColor = valueColor[0]
        colorEntryList.append(
            {'colors': valueColor, 'positions': valuePosition})
    sortedColorEntryList = sorted(colorEntryList, key=lambda x: x['positions'])
    for destKey in ['positions', 'colors']:
        parameter = xmlGroup.find(
            ".//group_parameter[@name='{param}']".format(param=destKey))
        if parameter is None:
            continue
        enableNode = parameter.find("*[@name='enable']")
        valueNode = parameter.find("*[@name='value']")
        enableNode.attrib['value'] = '1'
        tupleSize = int(valueNode.get('tupleSize', '0'))
        valueNode.attrib['size'] = str(tupleSize * colorEntryListSize)
        for i in range(colorEntryListSize):
            value = sortedColorEntryList[i][destKey]
            for j in range(tupleSize):
                subValue = ET.SubElement(valueNode, 'number_parameter')
                subValue.attrib['name'] = 'i' + str(i * tupleSize + j)
                subValue.attrib['value'] = str(
                    value[j] if tupleSize > 1 else value)


def overrideManifold2DParams(key, value):
    '''
    Special overrides.
    Katana expects UV Set name instead of 'u_uvSet'
    '''
    if key == 'primvarS':
        if value == 'u_uvSet':
            value = 'map2'
    elif key == 'primvarT':
        if value == 'v_uvSet':
            value = ''
    return value


# Preprocess keywords:
# - preprocess
# - postprocess (postprocess at level 0)
# - type (override type)
premap = {
    # Maya shading engine node
    'shadingEngine': {
        'type': 'networkMaterial',
        'preprocess': preprocessNetworkMaterial,
        'postprocess': postprocessNetworkMaterial,
    },
    # RenderMan nodes in an alphabetical order
    'aaOceanPrmanShader': {},
    'PxrAdjustNormal': {},
    'PxrAovLight': {},
    'PxrAttribute': {},
    'PxrBackgroundDisplayFilter': {},
    'PxrBackgroundSampleFilter': {},
    'PxrBakePointCloud': {},
    'PxrBakeTexture': {},
    'PxrBarnLightFilter': {},
    'PxrBlack': {},
    'PxrBlackBody': {},
    'PxrBlend': {},
    'PxrBlockerLightFilter': {},
    'PxrBump': {},
    'PxrBumpManifold2D': {},
    'PxrCamera': {},
    'PxrChecker': {},
    'PxrClamp': {},
    'PxrColorCorrect': {},
    'PxrCombinerLightFilter': {},
    'PxrConstant': {},
    'PxrCookieLightFilter': {},
    'PxrCopyAOVDisplayFilter': {},
    'PxrCopyAOVSampleFilter': {},
    'PxrCross': {},
    'PxrCryptomatte': {},
    'PxrDebugShadingContext': {},
    'PxrDefault': {},
    'PxrDiffuse': {},
    'PxrDirectLighting': {},
    'PxrDirt': {},
    'PxrDiskLight': {},
    'PxrDisney': {},
    'PxrDisplace': {
        'preprocess': preprocessDisplacement,
    },
    'PxrDispScalarLayer': {},
    'PxrDispTransform': {},
    'PxrDispVectorLayer': {},
    'PxrDisplayFilterCombiner': {},
    'PxrDistantLight': {},
    'PxrDomeLight': {},
    'PxrDot': {},
    'PxrEdgeDetect': {},
    'PxrEnvDayLight': {},
    'PxrExposure': {},
    'PxrFacingRatio': {},
    'PxrFilmicTonemapperDisplayFilter': {},
    'PxrFilmicTonemapperSampleFilter': {},
    'PxrFlakes': {},
    'PxrFractal': {},
    'PxrFractalize': {},
    'PxrGamma': {},
    'PxrGeometricAOVs': {},
    'PxrGlass': {},
    'PxrGoboLightFilter': {},
    'PxrGradeDisplayFilter': {},
    'PxrGradeSampleFilter': {},
    'PxrHSL': {},
    'PxrHair': {},
    'PxrHairColor': {},
    'PxrHalfBufferErrorFilter': {},
    'PxrImageDisplayFilter': {},
    'PxrImagePlaneFilter': {},
    'PxrIntMultLightFilter': {},
    'PxrInvert': {},
    'PxrLMDiffuse': {},
    'PxrLMGlass': {},
    'PxrLMLayer': {},
    'PxrLMMetal': {},
    'PxrLMMixer': {},
    'PxrLMPlastic': {},
    'PxrLMSubsurface': {},
    'PxrLayer': {},
    'PxrLayerMixer': {},
    'PxrLayerSurface': {
        'preprocess': preprocessUtilityPattern,
    },
    'PxrLayeredBlend': {},
    'PxrLayeredTexture': {},
    'PxrLightEmission': {},
    'PxrLightProbe': {},
    'PxrLightSaturation': {},
    'PxrManifold2D': {},
    'PxrManifold3D': {},
    'PxrManifold3DN': {},
    'PxrMarschnerHair': {},
    'PxrMatteID': {},
    'PxrMeshLight': {},
    'PxrMix': {},
    'PxrMultiTexture': {},
    'PxrNormalMap': {},
    'PxrOcclusion': {},
    'PxrPathTracer': {},
    'PxrPortalLight': {},
    'PxrPrimvar': {},
    'PxrProjectionLayer': {},
    'PxrProjectionStack': {},
    'PxrProjector': {},
    'PxrPtexture': {},
    'PxrRamp': {},
    'PxrRampLightFilter': {},
    'PxrRandomTextureManifold': {},
    'PxrRectLight': {},
    'PxrRemap': {},
    'PxrRodLightFilter': {},
    'PxrRollingShutter': {},
    'PxrRoundCube': {},
    'PxrSeExpr': {},
    'PxrShadedSide': {},
    'PxrShadowDisplayFilter': {},
    'PxrShadowFilter': {},
    'PxrSkin': {},
    'PxrSphereLight': {},
    'PxrSurface': {
        'preprocess': preprocessUtilityPattern,
    },
    'PxrTangentField': {},
    'PxrTee': {},
    'PxrTexture': {},
    'PxrThinFilm': {},
    'PxrThreshold': {},
    'PxrTileManifold': {},
    'PxrToFloat': {},
    'PxrToFloat3': {},
    'PxrVariable': {},
    'PxrVary': {},
    'PxrVolume': {},
    'PxrVoronoise': {},
    'PxrWhitePointDisplayFilter': {},
    'PxrWhitePointSampleFilter': {},
    'PxrWorley': {},
}

# Mappings keywords:
# - customColor
# - customProcess
# - customMapping
mappings = {
    'networkMaterial': {
        'customColor': (0.4, 0.35, 0.2),
        'customProcess': processNetworkMaterial,
    },
    'aaOceanPrmanShader': {},
    'PxrAdjustNormal': {},
    'PxrAovLight': {},
    'PxrAttribute': {},
    'PxrBackgroundDisplayFilter': {},
    'PxrBackgroundSampleFilter': {},
    'PxrBakePointCloud': {},
    'PxrBakeTexture': {},
    'PxrBarnLightFilter': {},
    'PxrBlack': {},
    'PxrBlackBody': {},
    'PxrBlend': {},
    'PxrBlockerLightFilter': {},
    'PxrBump': {},
    'PxrBumpManifold2D': {},
    'PxrCamera': {},
    'PxrChecker': {},
    'PxrClamp': {},
    'PxrColorCorrect': {},
    'PxrCombinerLightFilter': {},
    'PxrConstant': {},
    'PxrCookieLightFilter': {},
    'PxrCopyAOVDisplayFilter': {},
    'PxrCopyAOVSampleFilter': {},
    'PxrCross': {},
    'PxrCryptomatte': {},
    'PxrDebugShadingContext': {},
    'PxrDefault': {},
    'PxrDiffuse': {},
    'PxrDirectLighting': {},
    'PxrDirt': {},
    'PxrDiskLight': {},
    'PxrDisney': {},
    'PxrDisplace': {},
    'PxrDispScalarLayer': {},
    'PxrDispTransform': {},
    'PxrDispVectorLayer': {},
    'PxrDisplayFilterCombiner': {},
    'PxrDistantLight': {},
    'PxrDomeLight': {},
    'PxrDot': {},
    'PxrEdgeDetect': {},
    'PxrEnvDayLight': {},
    'PxrExposure': {},
    'PxrFacingRatio': {},
    'PxrFilmicTonemapperDisplayFilter': {},
    'PxrFilmicTonemapperSampleFilter': {},
    'PxrFlakes': {},
    'PxrFractal': {},
    'PxrFractalize': {},
    'PxrGamma': {},
    'PxrGeometricAOVs': {},
    'PxrGlass': {},
    'PxrGoboLightFilter': {},
    'PxrGradeDisplayFilter': {},
    'PxrGradeSampleFilter': {},
    'PxrHSL': {},
    'PxrHair': {},
    'PxrHairColor': {},
    'PxrHalfBufferErrorFilter': {},
    'PxrImageDisplayFilter': {},
    'PxrImagePlaneFilter': {},
    'PxrIntMultLightFilter': {},
    'PxrInvert': {},
    'PxrLMDiffuse': {},
    'PxrLMGlass': {},
    'PxrLMLayer': {},
    'PxrLMMetal': {},
    'PxrLMMixer': {},
    'PxrLMPlastic': {},
    'PxrLMSubsurface': {},
    'PxrLayer': {
        'customMapping': False,
        'customColor': (0.2, 0.36, 0.1),
    },
    'PxrLayerMixer': {},
    'PxrLayerSurface': {
        'customMapping': False,
        'customColor': (0.2, 0.36, 0.1),
    },
    'PxrLayeredBlend': {},
    'PxrLayeredTexture': {
        'customMapping': False,
        'customColor': (0.36, 0.25, 0.38),
        'filename': replaceTex,
    },
    'PxrLightEmission': {},
    'PxrLightProbe': {},
    'PxrLightSaturation': {},
    'PxrManifold2D': {
        'customMapping': False,
        'primvarS': overrideManifold2DParams,
        'primvarT': overrideManifold2DParams,
    },
    'PxrManifold3D': {},
    'PxrManifold3DN': {},
    'PxrMarschnerHair': {},
    'PxrMatteID': {},
    'PxrMeshLight': {},
    'PxrMix': {},
    'PxrMultiTexture': {
        'customMapping': False,
        'customColor': (0.36, 0.25, 0.38),
        'filename0': replaceTex,
        'filename1': replaceTex,
        'filename2': replaceTex,
        'filename3': replaceTex,
        'filename4': replaceTex,
        'filename5': replaceTex,
        'filename6': replaceTex,
        'filename7': replaceTex,
        'filename8': replaceTex,
        'filename9': replaceTex,
    },
    'PxrNormalMap': {},
    'PxrOcclusion': {},
    'PxrPathTracer': {},
    'PxrPortalLight': {},
    'PxrPrimvar': {},
    'PxrProjectionLayer': {},
    'PxrProjectionStack': {},
    'PxrProjector': {},
    'PxrPtexture': {
        'customMapping': False,
        'customColor': (0.36, 0.25, 0.38),
    },
    'PxrRamp': {
        'customProcess': processRamp,
        'rampType': None,
        'tile': None,
        # 'positions': None,
        # 'colors': None,
        'reverse': None,
        'basis': None,
        'splineMap': None,
        'randomSource': None,
        'randomSeed': None,
        'manifold': None,
    },
    'PxrRampLightFilter': {},
    'PxrRandomTextureManifold': {},
    'PxrRectLight': {},
    'PxrRemap': {},
    'PxrRodLightFilter': {},
    'PxrRollingShutter': {},
    'PxrRoundCube': {},
    'PxrSeExpr': {},
    'PxrShadedSide': {},
    'PxrShadowDisplayFilter': {},
    'PxrShadowFilter': {},
    'PxrSkin': {},
    'PxrSphereLight': {},
    'PxrSurface': {
        'customMapping': False,
        'customColor': (0.2, 0.36, 0.1),
    },
    'PxrTangentField': {},
    'PxrTee': {},
    'PxrTexture': {
        'customMapping': False,
        'customColor': (0.36, 0.25, 0.38),
        'filename': replaceTex,
    },
    'PxrThinFilm': {},
    'PxrThreshold': {},
    'PxrTileManifold': {},
    'PxrToFloat': {},
    'PxrToFloat3': {},
    'PxrVariable': {},
    'PxrVary': {},
    'PxrVolume': {},
    'PxrVoronoise': {},
    'PxrWhitePointDisplayFilter': {},
    'PxrWhitePointSampleFilter': {},
    'PxrWorley': {},
    'ShadingNodeArrayConnector': {
        'customProcess': processUtilityPattern,
    },
}
