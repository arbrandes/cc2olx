import re
import urllib
import xml.dom.minidom

from cc2olx.qti import QtiExport


class OlxExportException(Exception):
    """
    Exception type for errors during exporting normalized
    Common Cartridge data to OLX format.
    """


class OlxExport:
    """
    This class is used to convert intermediate representation
    of Common Cartridge to OLX.

    OLX guide: https://edx.readthedocs.io/projects/edx-open-learning-xml/en/latest/
    """

    # content types
    HTML = "html"
    LINK = "link"
    VIDEO = "video"
    LTI = "lti"
    QTI = "qti"

    def __init__(self, cartridge):
        self.cartridge = cartridge
        self.doc = None

    def xml(self):
        self.doc = xml.dom.minidom.Document()
        self.doc.appendChild(self.doc.createComment(" Generated by cc2olx "))

        xcourse = self.doc.createElement("course")
        xcourse.setAttribute("org", self.cartridge.get_course_org())
        xcourse.setAttribute("course", "Some_cc_Course")
        xcourse.setAttribute("name", self.cartridge.get_title())
        self.doc.appendChild(xcourse)

        tags = "chapter sequential vertical".split()
        self._add_olx_nodes(xcourse, self.cartridge.normalized['children'], tags)

        return self.doc.toprettyxml()

    def _add_olx_nodes(self, element, course_data, tags):
        """
        Recursively loops through the normalized common cartridge course data and
        adds appropriate OLX nodes to given course element.

        Expects `course_data` to be a list of triple nested elements that
        represent chapters in OLX courseware structure, like:
        ```
        [
            {
                'children': [        <----- chapter
                    'children': [        <----- sequential
                        'children': [        <----- vertical
                            ...content of vertical...
                        ]
                    ]
                ]
            }
        ]
        ```
        """

        leaf = not tags
        for element_data in course_data:
            if leaf:
                content_type, details = self._get_content(element_data)
                children = self._create_olx_nodes(content_type, details)
            else:
                children = [self.doc.createElement(tags[0])]

            for child in children:
                if "title" in element_data:
                    child.setAttribute("display_name", element_data["title"])

                element.appendChild(child)

                if "children" in element_data:
                    self._add_olx_nodes(child, element_data["children"], tags[1:])

    def _get_content(self, element_data):
        """
        Gets content type and details from element's data.
        """

        content_type = None
        details = None

        if "identifierref" in element_data:
            idref = element_data["identifierref"]
            content_type, details = self.cartridge.get_resource_content(idref)

        if content_type is None:
            content_type = self.HTML
            details = {
                "html": "<p>MISSING CONTENT</p>",
            }

        if content_type == self.LINK:
            content_type, details = process_link(details)

        return content_type, details

    def _process_static_links(self, html):
        srcs = re.findall(r'src\s*=\s*"(.+?)"', html)
        for src in srcs:
            if 'IMS-CC-FILEBASE' in src:
                new_src = urllib.parse.unquote(src).replace("$IMS-CC-FILEBASE$", "/static")
                html = html.replace(src, new_src)
        return html

    def _create_olx_nodes(self, content_type, details):
        """
        Based on content type and element details creates appropriate
        child nodes.
        """

        nodes = []

        if content_type == self.HTML:
            child = self.doc.createElement("html")
            html = self._process_static_links(details["html"])
            txt = self.doc.createCDATASection(html)
            child.appendChild(txt)

            nodes.append(child)

        elif content_type == self.VIDEO:
            child = self.doc.createElement("video")
            child.setAttribute("youtube", "1.00:" + details["youtube"])
            child.setAttribute("youtube_id_1_0", details["youtube"])

            nodes.append(child)

        elif content_type == self.LTI:
            nodes.append(self._create_lti_node(details))

        elif content_type == self.QTI:
            qti_export = QtiExport(self.doc)
            nodes += qti_export.create_qti_node(details)

        else:
            raise OlxExportException("Content type \"{}\" is not supported.".format(content_type))

        return nodes

    def _create_lti_node(self, details):
        node = self.doc.createElement('lti_consumer')
        custom_parameters = "[{params}]".format(
            params=', '.join([
                '"{key}={value}"'.format(
                    key=key,
                    value=value,
                )
                for key, value in details['custom_parameters'].items()
            ]),
        )
        node.setAttribute('custom_parameters', custom_parameters)
        node.setAttribute('description', details['description'])
        node.setAttribute('display_name', details['title'])
        node.setAttribute('inline_height', details['height'])
        node.setAttribute('inline_width', details['width'])
        node.setAttribute('launch_url', details['launch_url'])
        node.setAttribute('modal_height', details['height'])
        node.setAttribute('modal_width', details['width'])
        node.setAttribute('xblock-family', 'xblock.v1')
        return node


def process_link(details):
    """
    Possibly convert a link to a video.
    """

    # YouTube links can be like this: https://www.youtube.com/watch?v=gQ-cZRmHfs4&amp;amp;list=PL5B350D511278A56B
    ytmatch = re.search(r"youtube.com/watch\?v=([-\w]+)", details["href"])
    if ytmatch:
        return "video", {"youtube": ytmatch.group(1)}

    details = {
        "html": "<a href='{}'>{}</a>".format(details["href"], details.get("text", "")),
    }

    return "html", details
