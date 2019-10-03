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
    Copy shader nodes to Katana
    ------------------------------
'''

import os

import maya.cmds as cmds

from . import utils, ET

try:
    import PySide2
    CLIPBOARD = PySide2.QtGui.QGuiApplication.clipboard()
except (ImportError, AttributeError):
    try:
        import PySide
        CLIPBOARD = PySide.QtGui.QApplication.clipboard()
    except (ImportError, AttributeError):
        CLIPBOARD = None

BASEDIR = os.path.dirname(os.path.realpath(__file__))

KATANA_NODE_WIDTH = 200
KATANA_SPACE_WIDTH = 60
KATANA_ROW_HEIGHT = 100


def equal_attributes(a, b):
    '''
    Compare two attributes for equality
    '''
    delta = 0.001
    if isinstance(a, (list, tuple)):
        for val_a, val_b in zip(a, b):
            if not equal_attributes(val_a, val_b):
                return False
        return True
    elif isinstance(a, (str, unicode)) and isinstance(b, (list, tuple)):
        # Special case for RenderMan 21 inputMaterial
        # different data types in Maya and Katana
        if not a and not b:
            return True
        return False
    elif isinstance(a, float) and isinstance(b, (list, tuple)):
        # Special case for RenderMan 22 inputMaterial
        # different data types in Maya and Katana
        if not a and not b:
            return True
        return False
    elif isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < delta
    elif isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, tuple):
            a = bool(a)
        if isinstance(b, tuple):
            b = bool(b)
        if not isinstance(a, bool):
            a = (a == 'True') or int(a) == 1
        if not isinstance(b, bool):
            b = (b == 'True') or int(b) == 1
        return a == b
    elif isinstance(a, int) or isinstance(b, int):
        if isinstance(a, tuple):
            a = len(a)
        if isinstance(b, tuple):
            b = len(b)
        return int(a) == int(b)
    else:
        return a == b


def iterate_mapping_recursive(mapping_dict, xml_group, node):
    '''
    The most complicated part that maps
    Maya parameters to Katana XML parameters
    '''
    attributes = node['attributes']
    mapping = dict(mapping_dict)
    if not mapping or not mapping.get('customMapping', True):
        # If we know that the node has identical attributes
        # in both Maya and Katana, then we don't need the mapping dictionary,
        # we can build it on-the-fly from Maya node attributes
        attr_dict = dict.fromkeys(attributes)
        attr_dict.update(mapping)
        mapping = attr_dict
    # Special case: custom processing (used for ramp, etc.)
    custom_option = mapping.pop('customProcess', None)
    if custom_option:
        custom_option(xml_group, node)
    custom_option = mapping.pop('customColor', None)
    if custom_option:
        xml_group.attrib['ns_colorr'] = str(custom_option[0])
        xml_group.attrib['ns_colorg'] = str(custom_option[1])
        xml_group.attrib['ns_colorb'] = str(custom_option[2])
    for param_key, param_children in mapping.items():
        options = None
        process_field = None
        force_continue = False
        dest_key = param_key
        if isinstance(param_children, tuple):
            dest_key = param_children[0]
            param_children = param_children[1]
        if isinstance(param_children, list):
            options = param_children
            param_children = None
        if isinstance(param_children, str):
            dest_key = param_children
            param_children = None
            connections = node['connections']
            for connection_name, connection in connections.items():
                if connection_name == param_key:
                    connections[dest_key] = connection
                    connections.pop(connection_name)
                    break
        if callable(param_children):
            process_field = param_children
            param_children = None
        parameter = xml_group.find(
            ".//group_parameter[@name='parameters']"
            "//group_parameter[@name='{param}']".format(param=dest_key))
        # print param_key, dest_key, node
        if parameter is not None:
            enable_node = parameter.find("*[@name='enable']")
            type_node = parameter.find("string_parameter[@name='type']")
            # print parameter, enable_node, type_node
            parameter_type = ''
            if type_node is not None:
                parameter_type = type_node.get('value')
            value_node = parameter.find("*[@name='value']")
            tuples = None
            if value_node is not None:
                value = value_node.get('value')
                # print(param_key, value)
                if not value:
                    tuples = value_node.get('size')
                    if tuples:
                        value = ()
                        for i in range(int(tuples)):
                            sub_value = value_node.find(
                                "*[@name='i{index}']".format(index=i)).get(
                                    'value')
                            if parameter_type == 'FloatAttr':
                                sub_value = float(sub_value)
                            elif parameter_type == 'IntAttr':
                                sub_value = int(sub_value)
                            value += (sub_value,)
                maya_value = attributes.get(param_key)
                if isinstance(maya_value, list) and len(maya_value) == 1:
                    maya_value = maya_value[0]
                if utils.has_connection(node, dest_key):
                    maya_value = value
                    force_continue = True
                # if isinstance(maya_value, dict):
                #     source = maya_value['source']
                #     port_node = xml_group.find(
                #         ".//port[@name='{param}']".format(param=dest_key))
                #     if port_node is not None:
                #         port_node.attrib['source'] = source
                #     maya_value = value
                #     force_continue = True
                if options:
                    if maya_value is not None:
                        maya_value = options[maya_value]
                if process_field:
                    maya_value = process_field(param_key, maya_value)
                # print('maya_value = ' + repr(maya_value))
                # print(param_key + ' = ' + repr(value))
                if maya_value is not None and not equal_attributes(
                        maya_value,
                        value):
                    # print('\tnew value = ' + str(maya_value))
                    if tuples:
                        # # HACK START
                        # # A hack to avoid RenderMan bug
                        # # with not working PxrMultiTexture.optimizeIndirect
                        # if isinstance(maya_value, bool):
                        #     print repr(maya_value), repr(value), dest_key
                        #     maya_value = (maya_value, )
                        # # HACK END
                        # In the end I've changed the PxrMultiTexture.xml
                        # and PxrNormalMap.xml file to fix the affected checkbox
                        for i, val in enumerate(maya_value):
                            sub_value_node = value_node.find(
                                "*[@name='i{index}']".format(index=i))
                            sub_value_node.attrib['value'] = str(val)
                    else:
                        if isinstance(maya_value, bool):
                            maya_value = int(maya_value)
                        # print('\tnew value = ' + str(maya_value))
                        value_node.attrib['value'] = str(maya_value)
                    if enable_node is not None:
                        enable_node.attrib['value'] = '1'
                else:
                    # print('Default value found for "{key}": {value}'.format(
                    #     key=param_key,
                    #     value=value))
                    pass
                if maya_value == 0 and not force_continue:
                    # No need to continue processing
                    param_children = None
        if param_children:
            # if param_children is not None
            iterate_mapping_recursive(param_children, xml_group, node)


def preprocess_node(node_name, premap):
    '''
    Preprocessing a node.
    This is needed as some nodes (like ramp or bump) can be
    replaced by several other nodes for Katana.
    We return either one original node or several
    nodes if something was replaced during preprocessing
    '''
    node_type = cmds.nodeType(node_name)
    if node_type not in premap:
        return None
    nodes = {}
    attributes = utils.node_attributes(node_name)
    connections = {}
    node_connections = cmds.listConnections(
        node_name,
        source=True,
        destination=False,
        connections=True,
        plugs=True)
    if node_connections:
        for i in range(len(node_connections) / 2):
            conn_to = node_connections[i * 2]
            conn_to = conn_to[conn_to.find('.') + 1:]
            conn_from = node_connections[i * 2 + 1]
            connections[conn_to] = {
                'node': conn_from[:conn_from.find('.')],
                'original_port': conn_from[conn_from.find('.') + 1:]
            }

    node = {
        'name': node_name,
        'type': node_type,
        'attributes': attributes,
        'connections': connections,
        'renamings': {}
    }
    premap_settings = premap[node_type]
    for attr in ['type', 'postprocess']:
        if premap_settings.get(attr):
            node[attr] = premap_settings.get(attr)
    if premap_settings.get('preprocess'):
        preprocess_func = premap_settings.get('preprocess')
        if preprocess_func:
            preprocess_result = preprocess_func(node)
            if preprocess_result:
                nodes.update(preprocess_result)
    else:
        nodes[node['name']] = node
    return nodes


def process_node(node, renderer, mappings):
    '''
    Start individual node processing
    '''
    if 'name' not in node:
        return None
    node_name = utils.strip_namespace(node['name'])
    node_type = node['type']
    if node_type not in mappings:
        return None
    xml_path = os.path.join(
        BASEDIR,
        'renderer',
        renderer,
        'nodes',
        node_type + '.xml')
    if not os.path.isfile(xml_path) or mappings.get(node_type) is None:
        return None
    tree = ET.parse(xml_path)
    root = tree.getroot()
    root.attrib['name'] = node_name
    xml_node = root.find("./group_parameter/string_parameter[@name='name']")
    if xml_node is not None:
        xml_node.attrib['value'] = node_name
    iterate_mapping_recursive(mappings[node_type], root, node)
    return root


def is_connected(source, dest):
    '''
    Test if given nodes have common connections
    '''
    connections = dest.get('connections')
    if connections:
        for connection in connections.values():
            if source.get('name') == connection.get('node'):
                return True
    return False


def check_orphaned_nodes(tree, nodes, node):
    '''
    Check for orphaned nodes at root level
    '''
    # print('Checking ' + node['name'])
    if nodes[node['name']].get('weight'):
        node['weight'] = nodes[node['name']].get('weight')
    remove_list = []
    for leaf in tree['children']:
        # leaf_node = leaf['name']
        # print('-- Testing against ' + leaf_node)
        if is_connected(leaf, nodes[node['name']]):
            # print('   Reordering...')
            # print('   Before:' + str(tree))
            remove_list.append(leaf)
            node['children'].append(leaf)
            # print('   After:' + str(tree))
    for leaf in remove_list:
        tree['children'].remove(leaf)


def insert_node(tree, nodes, branch, node, level=0):
    '''
    Main processing starts here. The nodes are inserted one by one.
    We build a tree by finding a correct place for each new node dynamically
    Orphaned nodes are inserted at root level
    '''
    leaf_node = branch['name']
    if leaf_node in nodes:
        if is_connected(node, nodes[leaf_node]):
            # We have found the right place to add a child
            check_orphaned_nodes(tree, nodes, node)
            branch['children'].append(node)
            return True
    if branch['children']:
        for leaf in branch['children']:
            if insert_node(tree, nodes, leaf, node, level + 1):
                return True
    if level > 0:
        return False
    # insert at level 0 (root child)
    check_orphaned_nodes(tree, nodes, node)
    # print('++ Inserting ' + node['name'])
    branch['children'].append(node)
    return True


def build_tree(nodes):
    '''
    Build a tree from plain list of nodes
    '''
    tree = {'name': 'root', 'children': []}
    for node in nodes.values():
        if 'name' in node:
            insert_node(
                tree,
                nodes,
                tree,
                {'name': node['name'], 'children': []})
    calc_tree_width(tree)
    calc_tree_pos(tree)
    return tree


def export_tree(branch, nodes_xml, level=0):
    '''
    Recursively build XML
    '''
    result = []
    if branch['name'] in nodes_xml:
        nodes_xml[branch['name']].attrib['x'] = str(branch['x'])
        nodes_xml[branch['name']].attrib['y'] = str(KATANA_ROW_HEIGHT * level)
        result.append(nodes_xml[branch['name']])
    if branch['children']:
        for leaf in branch['children']:
            result += export_tree(leaf, nodes_xml, level + 1)
    return result


def print_tree(branch, level=0):
    '''
    Debug routine to print the resulting tree
    '''
    if branch['name']:
        print '  ' * level + branch['name']
    if branch['children']:
        for leaf in branch['children']:
            print_tree(leaf, level + 1)


def calc_tree_width(branch):
    '''
    Recursively update branches with their widths
    '''
    width = 0
    count = 0
    if branch['children']:
        for leaf in branch['children']:
            width += calc_tree_width(leaf)
            count += 1
        width += (count - 1) * KATANA_SPACE_WIDTH
        branch['width'] = width
    else:
        width = KATANA_NODE_WIDTH
        branch['width'] = width
    return width


def calc_tree_pos(branch, x=0):
    '''
    Recursively update nodes with their positions
    '''
    branch['x'] = x
    if branch['children']:
        pos = x - branch['width'] / 2
        for leaf in sorted(
                branch['children'],
                key=lambda x: x.get('weight', 0)):
            calc_tree_pos(leaf, pos + leaf['width'] / 2)
            pos += leaf['width'] + KATANA_SPACE_WIDTH


def connect_xml(node_xml, dest, source):
    '''
    Connect ports and return True on success
    '''
    port_node = node_xml.find(".//port[@name='{param}']".format(param=dest))
    if port_node is not None:
        conn_source = utils.get_out_connection(source)
        if conn_source:
            port_node.attrib['source'] = conn_source
        return True
    return False


def get_all_shading_nodes(nodes):
    '''
    Get a list of all connected shading nodes
    '''
    if not isinstance(nodes, list):
        nodes = [nodes]
    result_nodes = []
    while nodes:
        result_nodes += nodes
        nodes = cmds.listConnections(nodes, source=True, destination=False)
    return result_nodes


def establish_connections(nodes, nodes_xml):
    '''
    Try to establish all the original connections
    '''
    for node_name, node_xml in nodes_xml.items():
        for dest, source in nodes[node_name]['connections'].items():
            if connect_xml(node_xml, dest, source):
                continue
            incoming_port = nodes[node_name]['name'] + '.' + dest
            source_port = source.get('node') + '.' + source.get('original_port')
            utils.log.warning(
                'Incoming port "%s" not found '
                'while trying to establish connection '
                'from "%s"',
                incoming_port,
                source_port)


def generate_xml(node_names, renderer=None):
    '''
    Return a string containing a valid Katana XML
    or an empty string if nothing can be copied
    '''
    if not isinstance(node_names, list):
        node_names = [node_names]
    if not node_names:
        return ''
    # Let's prepare the katana frame to enclose our nodes
    xml_root = ET.Element('katana')
    xml_root.attrib['release'] = '2.6v4'
    xml_root.attrib['version'] = '2.6.2.000001'
    xml_exported_nodes = ET.SubElement(xml_root, 'node')
    xml_exported_nodes.attrib['name'] = '__SAVE_exportedNodes'
    xml_exported_nodes.attrib['type'] = 'Group'
    # Collect the whole network if shadingEngine node is selected alone
    probe_node = node_names[0]
    if (len(node_names) == 1
            and cmds.nodeType(node_names[0]) == 'shadingEngine'):
        shading_group = node_names[0]
        node_names = []
        surface_shader = ''
        if cmds.attributeQuery(
                'aiSurfaceShader',
                node=shading_group,
                exists=True):
            surface_shader = cmds.listConnections(
                shading_group + '.aiSurfaceShader')
        if not surface_shader:
            surface_shader = cmds.listConnections(
                shading_group + '.surfaceShader')
        if surface_shader:
            node_names += surface_shader
        volume_shader = ''
        if cmds.attributeQuery(
                'aiVolumeShader',
                node=shading_group,
                exists=True):
            volume_shader = cmds.listConnections(
                shading_group + '.aiVolumeShader')
        if not volume_shader:
            volume_shader = cmds.listConnections(
                shading_group + '.volumeShader')
        if volume_shader:
            node_names += volume_shader
        probe_node = surface_shader or volume_shader
        displacement_shader = cmds.listConnections(
            shading_group + '.displacementShader')
        if displacement_shader:
            node_names += displacement_shader
        node_names = get_all_shading_nodes(node_names)
        node_names.append(shading_group)
    if not renderer:
        shader_type = cmds.nodeType(probe_node)
        if shader_type.startswith('Pxr'):
            renderer = 'prman'
        elif shader_type.startswith(('ai', 'al')):
            renderer = 'arnold'
        else:
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
        utils.log.exception('Error loading "%s" renderer: %r', renderer, e)
        return ''
    # Collect the list of used node names to get unique names
    node_names = list(set(node_names))
    utils.unique_name(reset=node_names)
    preprocessed_nodes = {}
    for node_name in node_names:
        preprocessed_node = preprocess_node(
            node_name,
            premap=renderer_module.premap)
        if preprocessed_node:
            preprocessed_nodes.update(preprocessed_node)
    utils.rename_connections(preprocessed_nodes)
    utils.propagate_connection_weights(preprocessed_nodes)
    graph_tree = build_tree(preprocessed_nodes)
    should_update_tree = False
    for branch in graph_tree['children']:
        node_name = branch['name']
        node = preprocessed_nodes[node_name]
        if node.get('postprocess'):
            # Remove the affected node
            # and reinsert its postprocessed replacement
            preprocessed_nodes.pop(node_name, None)
            postprocess_func = node['postprocess']
            postprocessed_node = postprocess_func(node, preprocessed_nodes)
            preprocessed_nodes.update(postprocessed_node)
            should_update_tree = True
    if should_update_tree:
        utils.rename_connections(preprocessed_nodes)
        graph_tree = build_tree(preprocessed_nodes)
    nodes_xml = {}
    for node_name, node in preprocessed_nodes.items():
        node_xml = process_node(
            node,
            renderer=renderer,
            mappings=renderer_module.mappings)
        if node_xml is not None:
            nodes_xml[node_name] = node_xml
    establish_connections(preprocessed_nodes, nodes_xml)
    all_xml_nodes = export_tree(graph_tree, nodes_xml)
    for xml_node in all_xml_nodes:
        xml_exported_nodes.append(xml_node)
    if nodes_xml:
        return ET.tostring(xml_root)
    return ''


def copy(renderer=None):
    '''
    Main node copy routine, called from shelf/menu
    Usage: Select the shading nodes to copy and call clip.copy()
    Then paste to Katana
    '''
    if not CLIPBOARD:
        utils.log.info('Clipboard not available, sorry')
        return
    node_names = cmds.ls(selection=True)
    xml = generate_xml(node_names, renderer=renderer)
    if xml:
        CLIPBOARD.setText(xml)
        utils.log.info(
            'Successfully copied nodes to clipboard. '
            'You can paste them to Katana now.')
    else:
        utils.log.info('Nothing copied, sorry')
