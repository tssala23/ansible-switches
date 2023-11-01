import re
import pprint

physical_interface_types = [
    "gigabitethernet",
    "tengigabitethernet",
    "twentyfivegige",
    "fortygige",
    "hundredgige"
]

vlan_interface_types = [
    "vlan"
]

lag_interface_types = [
    "port-channel"
]

def OS9_PARSEINTFRANGE(s, sw_config):
    output = []  # output list will store all interfaces in the range

    s_parts = s.split(" ")  # Split input string into type and range parts
    s_type = s_parts[0]
    s_range_str = s_parts[1]

    s_rangelist = s_range_str.split(",")  # split by commas

    for range in s_rangelist:
        range_parts = range.split("-")  # split by dashes
        if len(range_parts) == 1:
            output.append(f"{s_type} {range}")  # no range here
        else:
            # this is a range (-)
            range_0 = range_parts[0]
            range_1 = range_parts[1]

            storing = False
            for line in sw_config:
                if line.startswith(f"interface {s_type} {range_0}"):
                    # found range_0
                    storing = True

                if storing and line.startswith("interface"):
                    line_parts = line.split(" ")
                    intf_label = " ".join(line_parts[1:])
                    output.append(intf_label)

                if line.startswith(f"interface {s_type} {range_1}"):
                    # found range_1
                    break

    return output

def OS9_GETEXTENDEDCFG(sw_config):
    output = []

    for line in sw_config:
        if line.startswith("!"):
            continue

        line_parts = line.split(" ")
        num_spaces = line_parts.count("")
        line_header = line_parts[num_spaces]
        
        if line_header == "untagged" or line_header == "tagged" or line_header == "channel-member":  #! any others?
            range_str = " ".join(line_parts[num_spaces + 1:])
            intf_list = OS9_PARSEINTFRANGE(range_str, sw_config)
            cfg_list = [f'{" " * num_spaces}{line_header} {i}' for i in intf_list]
            output += cfg_list
        else:
            output.append(line)

    return output

def OS9_GETINTFCONFIG(intf, sw_config):
    output = []

    search_label = f"interface {intf}"
    recording = False
    for line in sw_config:
        if line == search_label:
            recording = True
            continue

        if recording and not line.startswith(" "):
            break

        if recording:
            output.append(line.strip())

    return output

def OS9_GENERATEINTFCONFIG(intf_label, intf_fields, sw_config, managed_vlan_list):
    """
    This will generate a sequence of OS9 commands for a single interface based on existing and manifest config.

    :param intf_label: Name of interface
    :type intf_label: str
    :param intf_fields: Fields from manifest of interface
    :type intf_fields: str
    :param sw_config: Switch configuration lines
    :type sw_config: list
    :return list of os9 commands:
    :rtype: list
    """
    def os9_searchconfig(sw_config, search_keys, line_keys, intf_search, intf_index):
        """
        Searches through config lines for specific subitem "line keys" from parent "search keys"
        This is useful for finding existing VLAN/LACP mappins since OS9 does it backwards

        :param sw_config: Switch configuration lines
        :type sw_config: list
        :param search_keys: List of parent keys to find in the config
        :type search_keys: list
        :param line_keys: List of subitem items to find below the parent (no leading spaces)
        :type line_keys: list
        :param intf_search: name of interface to match
        :type intf_search: str
        :return: List of parents found that match a all keys
        :rtype: list
        """
        out = []

        search_keys = ["interface " + i for i in search_keys]

        cur_line = ""
        for line in sw_config:
            line_str = line.strip()
            if line_str.lower().startswith(tuple(search_keys)):
                cur_line = line
            elif line_str.startswith("interface") and cur_line != "":
                cur_line = ""

            if line_str.startswith(tuple(line_keys)) and cur_line != "":
                line_parts = line_str.split(" ")
                line_intf_label = " ".join(line_parts[1:])
                parent_label = " ".join(cur_line.split(" ")[intf_index[0]:intf_index[1]])

                if line_intf_label == intf_search:
                    # found interface
                    out.append(parent_label)

        return out

    def os9_name(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "name" attribute (only for VLAN interfaces)

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set name
        :rtype: list
        """

        out = []

        if "name" in man_fields:
            # Name attribute exists in the manifest
            conf_line = f"name {man_fields['name']}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)  # add to out only if not already in switch conf

        elif any(item.startswith("name") for item in running_fields) and not default_port:
            # Name attribute exists on the switch, but shouldn't
            out.append("no name")

        return out

    def os9_description(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "description" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set description
        :rtype: list
        """

        out = []

        if "description" in man_fields:
            # Description attribute exists in the manifest
            conf_line = f"description {man_fields['description']}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)  # add to out only if not already in switch conf

        elif any(item.startswith("description") for item in running_fields) and not default_port:
            # Description attribute exists on the switch, but shouldn't
            out.append("no description")
        
        return out

    def os9_state(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "state" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set state
        :rtype: list
        """

        out = []

        # Create a no prefix based on manifest value
        if "state" in man_fields and man_fields["state"] == "up":
            no_str = "no "
        else:
            no_str = ""

        conf_line = f"{no_str}shutdown"
        if conf_line not in running_fields or default_port:
            out.append(conf_line)  # add to out only if not already in switch conf

        return out
    
    def os9_mtu(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "mtu" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set mtu
        :rtype: list
        """

        out = []

        if "mtu" in man_fields:
            # mtu attribute exists in the manifest
            conf_line = f"mtu {str(intf_fields['mtu'])}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)  # add to out only if not already in switch conf

        elif any(item.startswith("mtu") for item in running_fields) and not default_port:
            # mtu attribute exists on the switch, but shouldn't
            out.append("no mtu")

        return out
    
    def os9_autoneg(intf_label, man_fields, running_fields, default_port):
        """
        Create OS9 commands for "autoneg" attribute

        :param intf_label: Name of interface
        :type intf_label: str
        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set autoneg
        :rtype: list
        """

        intf_type = intf_label.split(" ")[0].lower()

        if intf_type == "gigabitethernet" or intf_type == "tengigabitethernet":
            # support negotiation command
            conf_line = "negotiation auto"
        elif intf_type == "twentyfivegige":
            conf_line = "intf-type cr1 autoneg"
        elif intf_type == "fiftygige":
            conf_line = "intf-type cr2 autoneg"
        elif intf_type == "hundredgige" or intf_type == "fortygige":
            conf_line = "intf-type cr4 autoneg"

        out = []

        if "autoneg" in man_fields and not man_fields["autoneg"]:
            conf_line = f"no {conf_line}"

            if conf_line not in running_config or default_port:
                out.append(conf_line)

        elif any("autoneg" in i for i in running_fields) or any("negotiation" in i for i in running_fields):
            out.append(conf_line)

        return out
    
    def os9_fec(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "fec" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set fec
        :rtype: list
        """

        out = []

        # Create a no prefix based on manifest value
        if "fec" in man_fields:
            if man_fields["fec"]:
                conf_line = "fec enable"
            else:
                conf_line = "no fec enable"

            if conf_line not in running_fields or default_port:
                out.append(conf_line)
        elif any("fec" in i for i in running_fields):
            # fec field exists
            conf_line = "fec default"
            out.append(conf_line)

        return out
        
    def os9_ip4(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "ip4" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set ip4
        :rtype: list
        """

        out = []

        if "ip4" in man_fields:
            # ip4 attribute exists in the manifest
            conf_line = f"ip address {man_fields['ip4']}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)  # add to out only if not already in switch conf
            
        elif any(item.startswith("ip address") for item in running_fields) and not default_port:
            # ip4 attribute exists on the switch, but shouldn't
            out.append("no ip address")

        return out
        
    def os9_ip6(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "ip6" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set ip6
        :rtype: list
        """

        out = []

        if "ip6" in man_fields:
            # ip6 attribute exists in the manifest
            conf_line = f"ipv6 address {man_fields['ip6']}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)  # add to out only if not already in switch conf
            
        elif any(item.startswith("ipv6 address") for item in running_fields) and not default_port:
            # ip6 attribute exists on the switch, but shouldn't
            out.append("no ipv6 address")

        return out
        
    def os9_edgeport(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "edge-port" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set edge-port
        :rtype: list
        """

        out = []

        # Every edge port interface will be defined as an edge port for all 3 protocols
        os9_stp_types = ["rstp", "pvst", "mstp"]

        is_edgeport = "stp-edge" in man_fields and man_fields["stp-edge"]
        for stp_type in os9_stp_types:
            # Loop through each stp type available
            conf_line = f"spanning-tree {stp_type} edge-port"
            if is_edgeport:
                if conf_line not in running_fields or default_port:
                    out.append(conf_line)  # add to out only if not already in switch conf
            else:
                if conf_line in running_fields and not default_port:
                    out.append(f"no {conf_line}")

        return out

    def os9_portmode(man_fields, running_fields):
        """
        Create OS9 commands for "portmode" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :return: Tuple of <OS9 commands to set portmode>,<defaulted port>
        :rtype: tuple
        """

        out = []
        def_intf = False  # if true then the interface needs to be defaulted before continuing

        if "portmode" in man_fields:
            intf_portmode = intf_fields["portmode"]

            has_switchport = "switchport" in running_fields
            has_portmode = "portmode hybrid" in running_fields

            if intf_portmode == "hybrid":
                # for hybrid port, portmode hybrid needs to go first
                if not has_portmode:
                    out.append("portmode hybrid")

                    if has_switchport:
                        # You cannot apply portmode hybrid unless switchport doesn't exist
                        def_intf = True

            if not has_switchport or def_intf:
                out.append("switchport")  # only apply if not already on switch

            if not def_intf:
                # remove L3 fields since they are mutually exclusive if they exist
                if any(item.startswith("ip address") for item in running_fields):
                    out.insert(0, "no ip address")
                
                if any(item.startswith("ipv6 address") for item in running_fields):
                    out.insert(0, "no ipv6 address")
        else:
            if "switchport" in running_fields:
                def_intf = True

            if "portmode hybrid" in running_fields and not def_intf:
                out.append("no portmode hybrid")

        return out,def_intf

    def os9_untagged(intf_label, sw_config, man_fields, default_port, managed_vlan_list):
        """
        Create OS9 commands for "untagged" attribute

        :param intf_label: Label of the interface
        :type: str
        :param sw_config: Switch config lines
        :type: list
        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param defaulted: If true, this interface is defaulted before executing
        :type defaulted: boolean
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set untagged
        :rtype: list
        """

        out = []

        # clean old vlans
        if not default_port:
            # no need to clean vlans if interface is being defaulted
            existing_vlan_list = os9_searchconfig(sw_config, vlan_interface_types, ["untagged"], intf_label, (1,3))

            for existing_vlan in existing_vlan_list:
                vlan_id = existing_vlan.split(" ")[-1]
                if not ("untagged" in man_fields and man_fields["untagged"] == int(vlan_id)) and not vlan_id in managed_vlan_list:
                    # don't remove managed vlan assignement
                    cur_intf_cfg = []
                    
                    cur_intf_cfg.append(f"interface {existing_vlan}")
                    conf_line = f"no untagged {intf_label}"
                    cur_intf_cfg.append(conf_line)

                    out.append(cur_intf_cfg)

        if "untagged" in man_fields:
            untagged_vlan = str(man_fields["untagged"])
            vlan_intf_label = f"Vlan {untagged_vlan}"

            vlan_running_fields = OS9_GETINTFCONFIG(vlan_intf_label, sw_config)
            conf_line = f"untagged {intf_label}"

            if conf_line not in vlan_running_fields or default_port:
                cur_intf_cfg = []

                cur_intf_cfg.append(f"interface {vlan_intf_label}")
                cur_intf_cfg.append(conf_line)
                out.append(cur_intf_cfg)

        return out
    
    def os9_tagged(intf_label, sw_config, man_fields, default_port, managed_vlan_list):
        """
        Create OS9 commands for "tagged" attribute

        :param intf_label: Label of the interface
        :type: str
        :param sw_config: Switch config lines
        :type: list
        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param defaulted: If true, this interface is defaulted before executing
        :type defaulted: boolean
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set tagged
        :rtype: list
        """

        def getTaggedVlanList(tagList):
            """
            The manifest allows tagged vlans to be specified as a range like 1000:1010
            This method parses that

            :param tagList: String to be parsed
            :type tagList: str
            :return: List of each vlan in the list
            :rtype: list
            """

            out = []

            for list_item in tagList:
                item_parts = str(list_item).split(":")

                if len(item_parts) == 1:
                    out += item_parts
                else:
                    vlan_list = list(range(int(item_parts[0]), int(item_parts[1]) + 1))
                    out += map(str, vlan_list)

            return out

        out = []

        if "tagged" in man_fields:
            tagged_vllist = getTaggedVlanList(man_fields["tagged"])

        if not default_port:
            # no need to clean vlans if interface is being defaulted
            existing_vlan_list = os9_searchconfig(sw_config, vlan_interface_types, ["tagged"], intf_label, (1,3))

            for existing_vlan in existing_vlan_list:
                vlan_id = existing_vlan.split(" ")[-1]
                if not vlan_id in tagged_vllist and not vlan_id in managed_vlan_list:
                    # Don't remove managed vlan
                    cur_intf_cfg = []

                    cur_intf_cfg.append(f"interface {existing_vlan}")
                    conf_line = f"no tagged {intf_label}"
                    cur_intf_cfg.append(conf_line)

                    out.append(cur_intf_cfg)

        if "tagged" in man_fields:
            for cur_vlan in tagged_vllist:
                vlan_intf_label = f"Vlan {str(cur_vlan)}"

                vlan_running_fields = OS9_GETINTFCONFIG(vlan_intf_label, sw_config)
                conf_line = f"tagged {intf_label}"

                if conf_line not in vlan_running_fields or default_port:
                    cur_intf_cfg = []

                    cur_intf_cfg.append(f"interface {vlan_intf_label}")
                    cur_intf_cfg.append(conf_line)
                    out.append(cur_intf_cfg)

        return out

    def os9_lagmembers(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "lag-members" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set lag-members
        :rtype: list
        """

        out = []

        if "lag-members" in man_fields:
            channel_members = man_fields["lag-members"]

            for lag_member in channel_members:
                conf_line = f"channel-member {lag_member}"

                if conf_line not in running_fields or default_port:
                    out.append(conf_line)  # add channel member if not on switch

            for cfg_line in running_fields:
                if cfg_line.startswith("channel-member"):
                    mem_intf_label = " ".join(cfg_line.split(" ")[1:])
                    if mem_intf_label not in channel_members and not default_port:
                        conf_line = f"no channel-member {mem_intf_label}"
                        out.insert(0, conf_line)  # remove any existing channel members if they exist

        return out

    def os9_lacpmembersactive(intf_label, sw_config, man_fields):
        """
        Create OS9 commands for "lag-members-active" attribute

        :param intf_label: Label of the interface
        :type: str
        :param sw_config: Switch config lines
        :type: list
        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :return: List of OS9 commands to set lag-members-active
        :rtype: list
        """

        out = []

        # clean existing members
        existing_member_list = os9_searchconfig(sw_config, physical_interface_types, ["port-channel"], intf_label, (0,2))
        for existing_member in existing_member_list:
            if not("lacp-members-active" in man_fields and existing_member in man_fields["lacp-members-active"]):
                out.append(f"interface {existing_member}")
                conf_line = "no port-channel-protocol LACP"
                out.append(conf_line)

        if "lacp-members-active" in man_fields:
            channel_members = man_fields["lacp-members-active"]

            for lag_member in channel_members:
                lag_member_fields = OS9_GETINTFCONFIG(lag_member, sw_config)

                conf_line = f"{intf_label.lower()} mode active"
                if conf_line not in lag_member_fields:
                    cur_intf_cfg = []

                    cur_intf_cfg.append(f"interface {lag_member}")
                    cur_intf_cfg.append("port-channel-protocol LACP")
                    cur_intf_cfg.append(conf_line)

                    out.append(cur_intf_cfg)

        return out
    
    def os9_lacpmemberspassive(intf_label, sw_config, man_fields):
        """
        Create OS9 commands for "lag-members-passive" attribute

        :param intf_label: Label of the interface
        :type: str
        :param sw_config: Switch config lines
        :type: list
        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :return: List of OS9 commands to set lag-members-passive
        :rtype: list
        """

        out = []

        # clean existing members
        existing_member_list = os9_searchconfig(sw_config, physical_interface_types, ["port-channel"], intf_label, (0,2))
        for existing_member in existing_member_list:
            if not("lacp-members-passive" in man_fields and existing_member in man_fields["lacp-members-passive"]):
                out.append(f"interface {existing_member}")
                conf_line = "no port-channel-protocol LACP"
                out.append(conf_line)

        if "lacp-members-passive" in man_fields:
            channel_members = man_fields["lacp-members-passive"]

            for lag_member in channel_members:
                lag_member_fields = OS9_GETINTFCONFIG(lag_member, sw_config)

                conf_line = f"{intf_label.lower()} mode passive"
                if conf_line not in lag_member_fields:
                    cur_intf_cfg = []

                    cur_intf_cfg.append(f"interface {lag_member}")
                    cur_intf_cfg.append("port-channel-protocol LACP")
                    cur_intf_cfg.append(conf_line)

                    out.append(cur_intf_cfg)

        return out
    
    def os9_lacprate(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "lacp-rate" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set lacp-rate
        :rtype: list
        """

        out = []

        if "lacp-rate" in man_fields:
            if man_fields["lacp-rate"] == "fast":
                conf_line = "lacp fast-switchover"

                if conf_line not in running_fields or default_port:
                    out.append(conf_line)
            
        elif "lacp fast-switchover" in running_fields and not default_port:
            out.append("no lacp fast-switchover")

        return out
        
    def os9_mlag(man_fields, running_fields, default_port):
        """
        Create OS9 commands for "mlag" attribute

        :param man_fields: Manifest fields for current interface
        :type man_fields: dict
        :param running_fields: Interface attributes in the running config
        :type running_fields: list
        :param default_port: If true, this port is being defaulted
        :type default_port: boolean
        :return: List of OS9 commands to set mlag
        :rtype: list
        """

        out = []

        if "mlag" in man_fields:
            conf_line = f"vlt-peer-lag {man_fields['mlag'].lower()}"
            if conf_line not in running_fields or default_port:
                out.append(conf_line)
  
        elif any(item.startswith("vlt-peer-lag") for item in running_fields) and not default_port:
            out.append("no vlt-peer-lag")

        return out

    #
    # Combine all configuration for the interface
    #

    running_config = OS9_GETINTFCONFIG(intf_label, sw_config)

    cur_intf_cfg = []
    output = []

    portmode_out,default_port = os9_portmode(intf_fields, running_config)
    # General
    cur_intf_cfg += os9_name(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_description(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_state(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_mtu(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_autoneg(intf_label, intf_fields, running_config, default_port)
    cur_intf_cfg += os9_fec(intf_fields, running_config, default_port)
    # L3
    cur_intf_cfg += os9_ip4(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_ip6(intf_fields, running_config, default_port)
    # STP
    cur_intf_cfg += os9_edgeport(intf_fields, running_config, default_port)
    # LAG
    cur_intf_cfg += os9_lagmembers(intf_fields, running_config, default_port)
    cur_intf_cfg += os9_lacprate(intf_fields, running_config, default_port)

    # VLAN interfaces / L2
    cur_intf_cfg += portmode_out
    cur_intf_cfg += os9_mlag(intf_fields, running_config, default_port)

    untag_list = os9_untagged(intf_label, sw_config, intf_fields, default_port, managed_vlan_list)
    output += untag_list

    tag_list = os9_tagged(intf_label, sw_config, intf_fields, default_port, managed_vlan_list)
    output += tag_list

    # These change physical interfaces
    lacp_members_active_list = os9_lacpmembersactive(intf_label, sw_config, intf_fields)
    output += lacp_members_active_list

    lacp_members_passive_list = os9_lacpmemberspassive(intf_label, sw_config, intf_fields)
    output += lacp_members_passive_list

    # add interface config line
    if len(cur_intf_cfg) > 0:
        cur_intf_cfg.insert(0, f"interface {intf_label}")

        if default_port:
            intf_type = intf_label.split(" ")[0]
            if intf_type.lower() in physical_interface_types:
                # this is a physical interface
                cur_intf_cfg.insert(0, f"default interface {intf_label}")
            elif intf_type.lower() in lag_interface_types:
                # this is a port channel, so it just needs to be delete
                cur_intf_cfg.insert(0, f"no interface {intf_label}")

        output.insert(0, cur_intf_cfg)

    return output

def OS9_GETFANOUT(sw_config, intf):
    out = []

    return out

def OS9_FANOUTCFG(sw_config, manifest):
    """
    This method will create OS9 commands for fanout interfaces

    :param sw_config: Switch configuration
    :type sw_config: str
    :param manifest: YAML manifest
    :type manifest: dict
    :return: List of OS9 commands
    :rtype: list
    """

    conf_lines = sw_config["ansible_facts"]["ansible_net_config"].splitlines()
    conf_lines = OS9_GETEXTENDEDCFG(conf_lines)

    out = []

    manifest_stackunits = []  # hold existing stuff for 2nd for loop

    # Add fanouts that need to be added
    for intf,items in manifest.items():
        if "fanout" in items:
            # this is a fanout interface
            fanout_speed = items["fanout"]["speed"]
            fanout_type = items["fanout"]["type"]
            port_num = intf.split("/")[-1]

            conf_line_base = f"stack-unit 1 port {port_num} portmode {fanout_type}"
            manifest_stackunits.append(conf_line_base)
            conf_line = f"{conf_line_base} speed {fanout_speed}"
            manifest_stackunits.append(conf_line)

            if conf_line not in conf_lines and conf_line_base not in conf_lines:
                parent_port_num = f"1/{port_num}"
                search_pattern = rf'^interface .*{re.escape(parent_port_num)}$'
                search_matches = [line for line in conf_lines if re.match(search_pattern, line)]
                parent_port_label = " ".join(search_matches[0].split(" ")[1:])

                out.append(f"default interface {parent_port_label}")
                out.append(f"{conf_line} no-confirm")

    # Remove fanouts that need to be removed
    for line in [s for s in conf_lines if s.startswith("stack-unit 1 port")]:
        # loop through existing stack-units
        if line in manifest_stackunits:
            # supposed to be there
            continue

        line_parts = line.split(" ")
        port_num = line_parts[3]

        search_pattern = rf'^interface .*1/{port_num}/\d$'
        search_matches = [match_line for match_line in conf_lines if re.match(search_pattern, match_line)]

        for child_intf in search_matches:
            out.append(f"default {child_intf}")

        conf_line_index = line.find("speed")
        if conf_line_index == -1:
            conf_line = line
        else:
            conf_line = line[:conf_line_index - 1]

        out.append(f"no {conf_line} no-confirm")

    return out

def OS9_CLEANINTF(sw_config, manifest, vlans):
    """
    This method will create os9 commands to delete interfaces that have been removed from the manifest
    This can happen when a vlan interface or a port channel is deleted

    :param sw_config: existing switch config
    :type sw_config: str
    :param manifst: interface manifest from YAML
    :type manifest: dict
    :param vlans: vlan manifest from YAML
    :type vlans: dict
    :return: List of os9 commands
    :rtype: list
    """

    conf_lines = sw_config["ansible_facts"]["ansible_net_config"].splitlines()
    conf_lines = OS9_GETEXTENDEDCFG(conf_lines)

    search_keys = ["interface " + i for i in vlan_interface_types] + ["interface " + i for i in lag_interface_types]

    out = []

    for line in conf_lines:
        if line == "interface Vlan 1":
            # skip default vlan
            continue

        if line.lower().startswith(tuple(search_keys)):
            line_parts = line.split(" ")
            intf_type = line_parts[1]
            intf_num = line_parts[-1]
            intf_label = " ".join(line_parts[1:])

            not_manifest_vlan = intf_type == "Vlan" and int(intf_num) not in vlans
            not_manifest_lag = intf_type == "Port-channel" and intf_label not in manifest

            if not_manifest_vlan or not_manifest_lag:
                out.append(f"no {line}")

    return out

def OS9_GETCONFIG(sw_config, intf, vlans):
    """
    Main method which returns a 2d list of commands, where each nested list is an interface

    :param sw_config: Running switch config
    :type sw_config: str
    :param manifest: YAML manifest
    :type manifest: dict
    :param type: Type of manifest (vlan or intf)
    :type type: str
    :return: 2D List os os9 commands
    :rtype: list
    """

    conf_lines = sw_config["ansible_facts"]["ansible_net_config"].splitlines()
    conf_lines = OS9_GETEXTENDEDCFG(conf_lines)

    managed_vlan_list = [str(key) for key, value in vlans.items() if "managed" in value and value["managed"]]
    vlans = {"Vlan " + str(key): value for key, value in vlans.items()}
    manifest = merge_dicts(vlans, intf)

    out = []

    for key,fields in manifest.items():
        if "managed" in fields and fields["managed"]:
            # Don't edit managed interfaces
            continue

        if "fanout" in fields:
            # Skip fanouts
            continue

        intf_lines = OS9_GENERATEINTFCONFIG(key, fields, conf_lines, managed_vlan_list)
        if len(intf_lines) > 0:
            out += intf_lines

    #pprint.pprint(out)
    #exit(0)

    return out

def merge_dicts(dict1, dict2):
    """
    Merges 2 nested dicts together

    :param dict1: First dict
    :type dict1: dict
    :param dict2: Second dict
    :type dict2: dict
    :return: Merged dict
    :rtype: dict
    """

    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        return dict2

    merged = dict1.copy()

    for key, value in dict2.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged
class FilterModule(object):
    def filters(self):
        return {
            "OS9_GETCONFIG": OS9_GETCONFIG,
            "OS9_CLEANINTF": OS9_CLEANINTF,
            "OS9_FANOUTCFG": OS9_FANOUTCFG
        }
