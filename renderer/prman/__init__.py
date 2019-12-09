#!/usr/bin/python
"""
    maya2katana - RenderMan plugin
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
    Copy shader nodes to Katana
    ------------------------------
"""

import os
import re

import maya.cmds as cmds

from ... import utils, ET


def replace_tex(key, filepath):
    """
    Replace all texture paths with their .tex counterparts
    """
    root, ext = os.path.splitext(filepath)
    if ext:
        ext = ".tex"
    root = root.replace("\\", "/")
    return root + ext


def preprocess_utility_pattern(node):
    """
    Preprocess Utility Pattern surface connections
    """
    nodes = {}
    node_name = node["name"]
    connections = node["connections"]
    utility_patterns = {}
    for i in connections:
        utility_match = re.search(r"^utilityPattern\[(\d+)\]$", i)
        if not utility_match:
            continue
        utility_patterns[int(utility_match.group(1))] = connections.get(i)
    nodes[node_name] = node
    if len(utility_patterns) == 1:
        connections["utilityPattern"] = utility_patterns.values()[0]
        del connections["utilityPattern[{}]".format(utility_patterns.keys()[0])]
    elif len(utility_patterns) > 1:
        # We should create a ShadingNodeArrayConnector
        connector_name = utils.unique_name(node_name + "Connector")
        array_connections = {}
        for i in sorted(utility_patterns):
            array_connections["i" + str(i)] = utility_patterns.get(i)
            del connections["utilityPattern[{}]".format(i)]
        connector = {
            "name": connector_name,
            "type": "ShadingNodeArrayConnector",
            "attributes": {},
            "connections": array_connections,
            "renamings": {},
        }
        connections["utilityPattern"] = {
            "node": connector_name,
            "original_port": "out",
        }
        nodes[connector_name] = connector
    return nodes


def preprocess_network_material(node):
    """
    Preprocess shadingEngine node and remap correct attributes
    """
    nodes = {}
    node_name = node["name"]
    connections = node["connections"]
    new_connections = {}
    for i in ["surfaceShader", "volumeShader"]:
        connection = connections.get(i)
        if connection:
            new_connections["prmanBxdf"] = connection
            break
    displacement_connection = connections.get("displacementShader")
    if displacement_connection:
        new_connections["prmanDisplacement"] = displacement_connection
    nodes[node_name] = node
    node["connections"] = new_connections
    return nodes


def postprocess_network_material(node, all_nodes):
    """
    Rename the networkMaterial node and connect bump
    """
    nodes = {}
    prman_surface = node["connections"].get("prmanBxdf")
    if prman_surface:
        shader_node = all_nodes.get(prman_surface["node"])
        if shader_node:
            shader_node_name = shader_node["name"]
            # Remove the output node to reinsert it back with the new name
            all_nodes.pop(shader_node_name, None)
            material_name = shader_node_name
            shader_node_name += "_out"
            shader_node["name"] = shader_node_name
            nodes[shader_node_name] = shader_node
            node["name"] = material_name
            node["renamings"] = {
                material_name: {"name": shader_node_name},
            }
            nodes[material_name] = node
    return nodes


def process_network_material(xml_group, node):
    """
    Process NetworkMaterial to remove extra input ports
    """
    for i in [
        "prmanBxdf",
        "prmanDisplacement",
        "prmanDisplayfilter",
        "prmanIntegrator",
        "prmanLight",
        "prmanLightfilter",
        "prmanPattern",
        "prmanProjection",
        "prmanSamplefilter",
        "prmanCoshaders.coshader",
    ]:
        if i not in node["connections"]:
            parameter = xml_group.find("./port[@name='{param}']".format(param=i))
            xml_group.remove(parameter)


def preprocess_displacement(node):
    """
    Change the weight to move the displacement subtree to the right
    """
    nodes = {}
    node_name = node["name"]
    node["weight"] = 20
    nodes[node_name] = node
    return nodes


def get_ramp_attr(node_name, attr):
    """
    Translate the old attribute names if needed
    """
    if cmds.attributeQuery("colorRamp", node=node_name, exists=True):
        new_ramp_attributes = {
            r"^colors\[(\d+)\]$": r"^colorRamp\[(\d+)\]\.colorRamp_Color$",
            "colors[{index}]": "colorRamp[{index}].colorRamp_Color",
            "{node}.colors[{index}]": "{node}.colorRamp[{index}].colorRamp_Color",
            "{node}.positions[{index}]": "{node}.colorRamp[{index}].colorRamp_Position",
            "{node}.positions": "{node}.colorRamp",
        }
        attr = new_ramp_attributes.get(attr, attr)
    return attr


def preprocess_ramp(node):
    """
    Preprocess ramp
    Maya allows incoming connections instead of colors.
    Katana needs the ShadingNodeArrayConnector.
    """
    nodes = {}
    node_name = node["name"]
    connections = node["connections"]
    attributes = node["attributes"]
    colors = {}
    color_entry_list_size = cmds.getAttr(
        get_ramp_attr(node_name, "{node}.positions").format(node=node_name), size=True
    )
    for connection_name, connection in connections.items():
        colors_match = re.search(
            get_ramp_attr(node_name, r"^colors\[(\d+)\]$"), connection_name
        )
        if not colors_match:
            continue
        i = int(colors_match.group(1))
        connection["weight"] = i
        colors[i] = connection
    attributes["useNewRamp"] = 0
    nodes[node_name] = node
    if colors:
        # We should create a ShadingNodeArrayConnector
        connector_name = utils.unique_name(node_name + "Connector")
        array_connections = {}
        for i in range(color_entry_list_size):
            connection = colors.get(i)
            # We need to create a PxrHSL node for color knots
            if not connection:
                hsl_name = utils.unique_name(node_name + "HSL" + str(i))
                value_color = cmds.getAttr(
                    get_ramp_attr(node_name, "{node}.colors[{index}]").format(
                        node=node_name, index=i
                    )
                )
                value_color = value_color[0]
                hsl = {
                    "name": hsl_name,
                    "type": "PxrHSL",
                    "attributes": {"inputRGB": value_color,},
                    "connections": {},
                    "renamings": {},
                    "weight": i,
                }
                nodes[hsl_name] = hsl
                connection = {
                    "node": hsl_name,
                    "original_port": "resultRGB",
                }
            array_connections["i" + str(i)] = connection
            if i in colors:
                del connections[
                    get_ramp_attr(node_name, "colors[{index}]").format(index=i)
                ]
        connector = {
            "name": connector_name,
            "type": "ShadingNodeArrayConnector",
            "attributes": {},
            "connections": array_connections,
            "renamings": {},
        }
        connections["colors"] = {
            "node": connector_name,
            "original_port": "out",
        }
        nodes[connector_name] = connector
    return nodes


def process_ramp(xml_group, node):
    """
    Process PxrRamp
    """
    attributes = node["attributes"]
    node_name = node["name"]
    if not node_name:
        return
    node_type = node["type"]
    if not node_type:
        return
    color_entry_list_size = cmds.getAttr(
        get_ramp_attr(node_name, "{node}.positions").format(node=node_name), size=True
    )
    color_entry_list = []
    color_entry_list_indices = sorted(
        cmds.getAttr(
            get_ramp_attr(node_name, "{node}.positions").format(node=node_name),
            multiIndices=True,
        )
    )
    for i in color_entry_list_indices:
        value_position = cmds.getAttr(
            get_ramp_attr(node_name, "{node}.positions[{index}]").format(
                node=node_name, index=i
            )
        )
        value_color = cmds.getAttr(
            get_ramp_attr(node_name, "{node}.colors[{index}]").format(
                node=node_name, index=i
            )
        )
        value_color = value_color[0]
        color_entry_list.append({"colors": value_color, "positions": value_position})
    color_entry_list.sort(key=lambda x: x["positions"])
    for dest_key in ["positions", "colors"]:
        parameter = xml_group.find(
            ".//group_parameter[@name='{param}']".format(param=dest_key)
        )
        if parameter is None:
            continue
        enable_node = parameter.find("*[@name='enable']")
        value_node = parameter.find("*[@name='value']")
        enable_node.attrib["value"] = "1"
        tuple_size = int(value_node.get("tupleSize", "0"))
        value_node.attrib["size"] = str(tuple_size * color_entry_list_size)
        for i in range(color_entry_list_size):
            value = color_entry_list[i][dest_key]
            for j in range(tuple_size):
                sub_value = ET.SubElement(value_node, "number_parameter")
                sub_value.attrib["name"] = "i" + str(i * tuple_size + j)
                sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)


def override_manifold_2d_params(key, value):
    """
    Special overrides.
    Katana expects UV Set name instead of 'u_uvSet'
    """
    if key == "primvarS":
        if value == "u_uvSet":
            value = "map2"
    elif key == "primvarT":
        if value == "v_uvSet":
            value = ""
    return value


def override_primvar_cs(key, value):
    """
    Special overrides.
    Maya treats colorSet primvar as Cs
    """
    if value == "Cs":
        value = "colorSet"
    return value


def process_array_connector(xml_group, node):
    """
    Process ArrayConnector connections
    """
    connections = node["connections"]
    for connection_name in sorted(connections):
        in_port = ET.SubElement(xml_group, "port")
        in_port.attrib["name"] = connection_name
        in_port.attrib["type"] = "in"


# Preprocess keywords:
# - preprocess
# - postprocess (postprocess at level 0)
# - type (override type)
premap = {
    # Maya shading engine node
    "shadingEngine": {
        "type": "networkMaterial",
        "preprocess": preprocess_network_material,
        "postprocess": postprocess_network_material,
    },
    # RenderMan nodes in an alphabetical order
    "aaOceanPrmanShader": {},
    "PxrAdjustNormal": {},
    "PxrAovLight": {},
    "PxrAttribute": {},
    "PxrBackgroundDisplayFilter": {},
    "PxrBackgroundSampleFilter": {},
    "PxrBakePointCloud": {},
    "PxrBakeTexture": {},
    "PxrBarnLightFilter": {},
    "PxrBlack": {},
    "PxrBlackBody": {},
    "PxrBlend": {},
    "PxrBlockerLightFilter": {},
    "PxrBump": {},
    "PxrBumpManifold2D": {},
    "PxrCamera": {},
    "PxrChecker": {},
    "PxrClamp": {},
    "PxrColorCorrect": {},
    "PxrCombinerLightFilter": {},
    "PxrConstant": {},
    "PxrCookieLightFilter": {},
    "PxrCopyAOVDisplayFilter": {},
    "PxrCopyAOVSampleFilter": {},
    "PxrCross": {},
    "PxrCryptomatte": {},
    "PxrCurvature": {},
    "PxrDebugShadingContext": {},
    "PxrDefault": {},
    "PxrDiffuse": {},
    "PxrDirectLighting": {},
    "PxrDirt": {},
    "PxrDiskLight": {},
    "PxrDisney": {},
    "PxrDisplace": {"preprocess": preprocess_displacement,},
    "PxrDispScalarLayer": {},
    "PxrDispTransform": {},
    "PxrDispVectorLayer": {},
    "PxrDisplayFilterCombiner": {},
    "PxrDistantLight": {},
    "PxrDomeLight": {},
    "PxrDot": {},
    "PxrEdgeDetect": {},
    "PxrEnvDayLight": {},
    "PxrExposure": {},
    "PxrFacingRatio": {},
    "PxrFilmicTonemapperDisplayFilter": {},
    "PxrFilmicTonemapperSampleFilter": {},
    "PxrFlakes": {},
    "PxrFractal": {},
    "PxrFractalize": {},
    "PxrGamma": {},
    "PxrGeometricAOVs": {},
    "PxrGlass": {},
    "PxrGoboLightFilter": {},
    "PxrGradeDisplayFilter": {},
    "PxrGradeSampleFilter": {},
    "PxrHSL": {},
    "PxrHair": {},
    "PxrHairColor": {},
    "PxrHalfBufferErrorFilter": {},
    "PxrImageDisplayFilter": {},
    "PxrImagePlaneFilter": {},
    "PxrIntMultLightFilter": {},
    "PxrInvert": {},
    "PxrLMDiffuse": {},
    "PxrLMGlass": {},
    "PxrLMLayer": {},
    "PxrLMMetal": {},
    "PxrLMMixer": {},
    "PxrLMPlastic": {},
    "PxrLMSubsurface": {},
    "PxrLayer": {},
    "PxrLayerMixer": {},
    "PxrLayerSurface": {"preprocess": preprocess_utility_pattern,},
    "PxrLayeredBlend": {},
    "PxrLayeredTexture": {},
    "PxrLightEmission": {},
    "PxrLightProbe": {},
    "PxrLightSaturation": {},
    "PxrManifold2D": {},
    "PxrManifold3D": {},
    "PxrManifold3DN": {},
    "PxrMarschnerHair": {},
    "PxrMatteID": {},
    "PxrMeshLight": {},
    "PxrMix": {},
    "PxrMultiTexture": {},
    "PxrNormalMap": {},
    "PxrOcclusion": {},
    "PxrPathTracer": {},
    "PxrPortalLight": {},
    "PxrPrimvar": {},
    "PxrProjectionLayer": {},
    "PxrProjectionStack": {},
    "PxrProjector": {},
    "PxrPtexture": {},
    "PxrRamp": {"preprocess": preprocess_ramp,},
    "PxrRampLightFilter": {},
    "PxrRandomTextureManifold": {},
    "PxrRectLight": {},
    "PxrRemap": {},
    "PxrRodLightFilter": {},
    "PxrRollingShutter": {},
    "PxrRoundCube": {},
    "PxrSeExpr": {},
    "PxrShadedSide": {},
    "PxrShadowDisplayFilter": {},
    "PxrShadowFilter": {},
    "PxrSkin": {},
    "PxrSphereLight": {},
    "PxrSurface": {"preprocess": preprocess_utility_pattern,},
    "PxrTangentField": {},
    "PxrTee": {},
    "PxrTexture": {},
    "PxrThinFilm": {},
    "PxrThreshold": {},
    "PxrTileManifold": {},
    "PxrToFloat": {},
    "PxrToFloat3": {},
    "PxrVariable": {},
    "PxrVary": {},
    "PxrVolume": {},
    "PxrVoronoise": {},
    "PxrWhitePointDisplayFilter": {},
    "PxrWhitePointSampleFilter": {},
    "PxrWorley": {},
}

# Mappings keywords:
# - customColor
# - customProcess
# - customMapping
mappings = {
    "networkMaterial": {
        "customColor": (0.4, 0.35, 0.2),
        "customProcess": process_network_material,
    },
    "aaOceanPrmanShader": {},
    "PxrAdjustNormal": {},
    "PxrAovLight": {},
    "PxrAttribute": {},
    "PxrBackgroundDisplayFilter": {},
    "PxrBackgroundSampleFilter": {},
    "PxrBakePointCloud": {},
    "PxrBakeTexture": {},
    "PxrBarnLightFilter": {},
    "PxrBlack": {},
    "PxrBlackBody": {},
    "PxrBlend": {},
    "PxrBlockerLightFilter": {},
    "PxrBump": {},
    "PxrBumpManifold2D": {},
    "PxrCamera": {},
    "PxrChecker": {},
    "PxrClamp": {},
    "PxrColorCorrect": {},
    "PxrCombinerLightFilter": {},
    "PxrConstant": {},
    "PxrCookieLightFilter": {},
    "PxrCopyAOVDisplayFilter": {},
    "PxrCopyAOVSampleFilter": {},
    "PxrCross": {},
    "PxrCryptomatte": {},
    "PxrCurvature": {},
    "PxrDebugShadingContext": {},
    "PxrDefault": {},
    "PxrDiffuse": {},
    "PxrDirectLighting": {},
    "PxrDirt": {},
    "PxrDiskLight": {},
    "PxrDisney": {},
    "PxrDisplace": {},
    "PxrDispScalarLayer": {},
    "PxrDispTransform": {},
    "PxrDispVectorLayer": {},
    "PxrDisplayFilterCombiner": {},
    "PxrDistantLight": {},
    "PxrDomeLight": {},
    "PxrDot": {},
    "PxrEdgeDetect": {},
    "PxrEnvDayLight": {},
    "PxrExposure": {},
    "PxrFacingRatio": {},
    "PxrFilmicTonemapperDisplayFilter": {},
    "PxrFilmicTonemapperSampleFilter": {},
    "PxrFlakes": {},
    "PxrFractal": {},
    "PxrFractalize": {},
    "PxrGamma": {},
    "PxrGeometricAOVs": {},
    "PxrGlass": {},
    "PxrGoboLightFilter": {},
    "PxrGradeDisplayFilter": {},
    "PxrGradeSampleFilter": {},
    "PxrHSL": {},
    "PxrHair": {},
    "PxrHairColor": {},
    "PxrHalfBufferErrorFilter": {},
    "PxrImageDisplayFilter": {},
    "PxrImagePlaneFilter": {},
    "PxrIntMultLightFilter": {},
    "PxrInvert": {},
    "PxrLMDiffuse": {},
    "PxrLMGlass": {},
    "PxrLMLayer": {},
    "PxrLMMetal": {},
    "PxrLMMixer": {},
    "PxrLMPlastic": {},
    "PxrLMSubsurface": {},
    "PxrLayer": {"customMapping": False, "customColor": (0.2, 0.36, 0.1),},
    "PxrLayerMixer": {},
    "PxrLayerSurface": {"customMapping": False, "customColor": (0.2, 0.36, 0.1),},
    "PxrLayeredBlend": {},
    "PxrLayeredTexture": {
        "customMapping": False,
        "customColor": (0.36, 0.25, 0.38),
        "filename": replace_tex,
    },
    "PxrLightEmission": {},
    "PxrLightProbe": {},
    "PxrLightSaturation": {},
    "PxrManifold2D": {
        "customMapping": False,
        "primvarS": override_manifold_2d_params,
        "primvarT": override_manifold_2d_params,
    },
    "PxrManifold3D": {},
    "PxrManifold3DN": {},
    "PxrMarschnerHair": {},
    "PxrMatteID": {},
    "PxrMeshLight": {},
    "PxrMix": {},
    "PxrMultiTexture": {
        "customMapping": False,
        "customColor": (0.36, 0.25, 0.38),
        "filename0": replace_tex,
        "filename1": replace_tex,
        "filename2": replace_tex,
        "filename3": replace_tex,
        "filename4": replace_tex,
        "filename5": replace_tex,
        "filename6": replace_tex,
        "filename7": replace_tex,
        "filename8": replace_tex,
        "filename9": replace_tex,
    },
    "PxrNormalMap": {},
    "PxrOcclusion": {},
    "PxrPathTracer": {},
    "PxrPortalLight": {},
    "PxrPrimvar": {"customMapping": False, "varname": override_primvar_cs,},
    "PxrProjectionLayer": {},
    "PxrProjectionStack": {},
    "PxrProjector": {},
    "PxrPtexture": {"customMapping": False, "customColor": (0.36, 0.25, 0.38),},
    "PxrRamp": {
        "customProcess": process_ramp,
        "rampType": None,
        "useNewRamp": None,
        "tile": None,
        # 'positions': None,
        # 'colors': None,
        "reverse": None,
        "basis": None,
        "splineMap": None,
        "randomSource": None,
        "randomSeed": None,
        "manifold": None,
    },
    "PxrRampLightFilter": {},
    "PxrRandomTextureManifold": {},
    "PxrRectLight": {},
    "PxrRemap": {},
    "PxrRodLightFilter": {},
    "PxrRollingShutter": {},
    "PxrRoundCube": {},
    "PxrSeExpr": {},
    "PxrShadedSide": {},
    "PxrShadowDisplayFilter": {},
    "PxrShadowFilter": {},
    "PxrSkin": {},
    "PxrSphereLight": {},
    "PxrSurface": {"customMapping": False, "customColor": (0.2, 0.36, 0.1),},
    "PxrTangentField": {},
    "PxrTee": {},
    "PxrTexture": {
        "customMapping": False,
        "customColor": (0.36, 0.25, 0.38),
        "filename": replace_tex,
    },
    "PxrThinFilm": {},
    "PxrThreshold": {},
    "PxrTileManifold": {},
    "PxrToFloat": {},
    "PxrToFloat3": {},
    "PxrVariable": {},
    "PxrVary": {},
    "PxrVolume": {},
    "PxrVoronoise": {},
    "PxrWhitePointDisplayFilter": {},
    "PxrWhitePointSampleFilter": {},
    "PxrWorley": {},
    "ShadingNodeArrayConnector": {"customProcess": process_array_connector,},
}
