import os, subprocess
import sys
import pcs
import xml.dom.minidom
from xml.dom.minidom import parseString


# usefile & filename variables are set in pcs module
usefile = False
filename = ""

# Run command, with environment and return (output, retval)
def run(args):
    env_var = os.environ
    if usefile:
        env_var["CIB_file"] = filename

        if not os.path.isfile(filename):
            try:
                write_empty_cib(filename)
            except IOError:
                print "Unable to write to file: " + filename
                sys.exit(1)

    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env = env_var)
        output = p.stdout.read()
        p.wait()
        returnVal = p.returncode
    except OSError:
        print "Unable to locate command: " + args[0]
        sys.exit(1)

    return output, returnVal

# Check is something exists in the CIB, if it does return it, if not, return
#  an empty string
def does_exist(xpath_query):
    args = ["cibadmin", "-Q", "--xpath", xpath_query]
    output,retval = run(args)
    if (retval != 0):
        return False
    return True

# Return matches from the CIB with the xpath_query
def get_cib_xpath(xpath_query):
    args = ["cibadmin", "-Q", "--xpath", xpath_query]
    output,retval = run(args)
    if (retval != 0):
        return ""
    return output

# Create an object in the cib
# Returns output, retval
def add_to_cib(scope, xml):
    args = ["cibadmin"]
    args = args  + ["-o", "resources", "-C", "-X", xml]
    return run(args)

# If the property exists, remove it and replace it with the new property
def set_cib_property(prop, value):
    crm_config = get_cib_xpath("//crm_config")
    if (crm_config == ""):
        print "Unable to get crm_config, is pacemaker running?"
        sys.exit(1)
    document = parseString(crm_config)
    crm_config = document.documentElement
    cluster_property_set = crm_config.getElementsByTagName("cluster_property_set")[0]
    property_exists = False
    for child in cluster_property_set.childNodes:
        if (child.nodeType != xml.dom.minidom.Node.ELEMENT_NODE):
            break
        if (child.getAttribute("id") == "cib-bootstrap-options-" + prop):
            cluster_property_set.removeChild(child)
            property_exists = True
            break

    new_property = document.createElement("nvpair")
    new_property.setAttribute("id","cib-bootstrap-options-"+prop)
    new_property.setAttribute("name",prop)
    new_property.setAttribute("value",value)
    cluster_property_set.appendChild(new_property)


    args = ["cibadmin", "-c", "-M", "--xml-text", cluster_property_set.toxml()]
    output, retVal = run(args)
    print output



def write_empty_cib(filename):

    empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
<cib admin_epoch="0" epoch="1" num_updates="1" validate-with="pacemaker-1.2">
  <configuration>
    <crm_config/>
    <nodes/>
    <resources/>
    <constraints/>
  </configuration>
  <status/>
</cib>"""
    f = open(filename, 'w')
    f.write(empty_xml)
    f.close()
