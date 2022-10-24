def os9_getLabelMap(sw_facts):
    label_map = {}

    split_conf = sw_facts.split("\n")
    intf_conf = [i for i in split_conf if i.startswith('interface')]

    for intf in intf_conf:
        intf_parts = intf.split(" ")
        label_map[intf_parts[2]] = " ".join(intf_parts[1:2])

    return label_map

def getSpacesInStartOfString(s):
    return len(s) - len(s.lstrip())

def os9_recurseLines(index, split_conf):
    out = {}

    trimmed_split_conf = split_conf[index:]
    numIndex = getSpacesInStartOfString(trimmed_split_conf[0])

    lastLine = ""
    skipint = 0
    for i, line in enumerate(trimmed_split_conf):
        if skipint > 0:
            skipint -= 1
            continue

        if "!" in line:
            continue

        cur_numSpaces = getSpacesInStartOfString(line)

        # remove whitespace after counting
        line = line.strip()

        if cur_numSpaces < numIndex:
            # we're done with this section
            return i - 1,out

        if cur_numSpaces == numIndex:
            # we can add this directly
            out[line] = {}

        if cur_numSpaces > numIndex:
            # start a new recursion
            rec_line = os9_recurseLines(i, trimmed_split_conf)

            print(rec_line)

            out[lastLine] = rec_line[1]
            skipint = rec_line[0]  # skip the lines that were covered by the recursion

        lastLine = line
        lastIndex = i

    return lastIndex - 1,out


def os9_getFactDict(sw_facts):
    split_conf = sw_facts["ansible_facts"]["ansible_net_config"].splitlines()

    return os9_recurseLines(0, split_conf)[1]
