#!/usr/bin/env python
# -*- coding: utf-8 -*-

import idna
import json
import munidata
import os
import picu
import pkgconfig
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from lgr.parser.xml_parser import XMLParser
from munidata import UnicodeDataVersionManager
from pprint import pprint
from urllib.parse import urlparse, unquote

class LGRServer(BaseHTTPRequestHandler):

    #
    # static properties
    #
    charset     = "utf-8"
    unimanager  = UnicodeDataVersionManager()
    lgr_dir     = "{}/lgrs".format(os.path.abspath(os.path.dirname(__file__)))
    lgrs        = {}
    server_addr = "0.0.0.0"
    server_port = 8080
    sets        = ["root-zone", "second-level-reference", "full-variant-set"]

    #
    # static methods
    #

    def run():
        """
        run the server
        """

        LGRServer.init_icu()

        server = ThreadingHTTPServer(
            server_address=(LGRServer.server_addr, LGRServer.server_port),
            RequestHandlerClass=LGRServer
        )

        print("Server running on http://{0}:{1}".format(
            LGRServer.server_addr,
            LGRServer.server_port
        ))

        try:
            server.serve_forever()

        except KeyboardInterrupt:
            exit()

    def init_icu():
        """
        picu and munidata need to know some information about the version of
        ICU we're using. this method works that stuff out
        """

        LGRServer.icu_libver = int(float(pkgconfig.modversion("icu-uc")))
        print("Detected ICU version {}.".format(LGRServer.icu_libver))

        if str(LGRServer.icu_libver) not in picu.loader.KNOWN_ICU_VERSIONS:
            print("Note: monkey patching picu.loader.KNOWN_ICU_VERSIONS")
            picu.loader.KNOWN_ICU_VERSIONS = picu.loader.KNOWN_ICU_VERSIONS + (str(LGRServer.icu_libver),)

        if not hasattr(munidata.idna.idnatables.IDNA_UNICODE_MAPPING, "15.0.0"):
            print("Note: monkey patching munidata.idna.idnatables.IDNA_UNICODE_MAPPING")
            munidata.idna.idnatables.IDNA_UNICODE_MAPPING["15.0.0"] = munidata.idna.idnatables.IDNA_UNICODE_MAPPING["12.1.0"]

        findcmd = [
            "find",
            "/usr/lib",
            "-regextype", "sed",
            "-iregex", ".*/libicu\\(uc\\|i18n\\).so.{0}".format(LGRServer.icu_libver)
        ]

        libs = {}
        for path in subprocess.check_output(findcmd).decode(LGRServer.charset).strip().split("\n"):
            libs[os.path.splitext(os.path.basename(path))[0]] = path

        LGRServer.icu_libpath = libs["libicuuc.so"]
        LGRServer.icu_i18n_libpath = libs["libicui18n.so"]

    def get_lgr(set, tag):
        """
        this method instantiates an LGR object for the given set/tag, using an
        in-memory cache to speed things up
        """

        key = "{0}.{1}".format(set, tag)

        if not hasattr(LGRServer.lgrs, key):
            LGRServer.lgrs[key] = None

            file = "{0}/{1}/{2}.xml".format(
                LGRServer.lgr_dir,
                set,
                tag
            )

            if os.path.exists(file):
                parser = XMLParser(file)

                parser.unicode_database = LGRServer.unimanager.register(
                    None,
                    LGRServer.icu_libpath,
                    LGRServer.icu_i18n_libpath,
                    LGRServer.icu_libver
                )

                LGRServer.lgrs[key] = parser.parse_document()

        return LGRServer.lgrs[key]

    #
    # instance methods
    #

    def respond(self, code=200, body=""):
        """
        construct a response and send it to the client
        """

        self.send_response(code)
        self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(body.encode(LGRServer.charset))

    def _error(self, code=400, message="Bad Request"):
        """
        construct an error response
        """
        self.respond(code, json.dumps({"error": code, "message": message}, indent=2))

    def do_GET(self):
        """
        handle GET request
        """

        segments = unquote(urlparse(self.path).path[1:], LGRServer.charset).split("/")

        if (len(segments) < 3 or len(segments) > 5):
            return self._error(400, "Invalid path '{}'".format(self.path))

        set = segments.pop(0)
        if set not in LGRServer.sets:
            return self._error(404, "Invalid LGR set '{}'".format(set))

        tag = segments.pop(0)
        if not re.match(r"^([a-z]{2,3})(-[A-Za-z]{4})?$", tag):
            # apart from ensuring that `tag` is likely to match a language tag
            # this prevents directory traversal attacks
            return self._error(400, "Invalid tag '{}'".format(tag))

        segment = segments.pop(0)
        if re.match("^xn--", segment, re.IGNORECASE):
            a_label = segment

        else:
            try:
                a_label = idna.encode(segment).decode(LGRServer.charset)

            except:
                return self.send_response(404, "Invalid U-label '{}'".format(segment))

        try:
            code_points = tuple([ord(c) for c in idna.decode(a_label)])

        lgr = LGRServer.get_lgr(set, tag)

        if lgr is None:
            return self._error(404, "Unknown LGR '{}'".format(tag))

        except:
            return self._error(404, "Invalid label '{}'".format(a_label))

        (eligible, _, invalid_code_points, disposition, _, _) = lgr.test_label_eligible(
            code_points,
            is_variant=False,
            collect_log=False
        )

        if 0 == len(segments):
            return self.label_info(
                tag,
                lgr,
                a_label,
                code_points,
                eligible,
                invalid_code_points,
                disposition
            )

        elif "variants" != segments.pop(0):
            return self._error(400, "Invalid path '{}'".format(self.path))

        elif not eligible:
            return self._error(404, "Invalid label '{}'".format(a_label))

        else:
            return self.label_variants(lgr, a_label, code_points)

    def label_info(self, tag, lgr, a_label, code_points, eligible, invalid_code_points, disposition):
        try:
            index_label = idna.encode("".join(map(chr, lgr.generate_index_label(code_points)))).decode(LGRServer.charset)
            approx_variants = lgr.estimate_variant_number(code_points)

        except:
            index_label = None
            approx_variants = 0

        u_label = "".join(map(chr, code_points))

        response = {
            "u_label":              u_label,
            "a_label":              a_label,
            "code_points":          code_points,
            "tag":                  tag,
            "invalid_code_points":  list(map(lambda cp: cp[0], invalid_code_points)),
            "eligible":             eligible,
            "disposition":          disposition,
            "index_label":          index_label,
            "is_index_label":       u_label == index_label,
            "approx_variants":      approx_variants,
        }

        return self.respond(200, json.dumps(response))

    def label_variants(self, lgr, a_label, code_points):
        variant_labels = lgr.compute_label_disposition(
            code_points,
            include_invalid=True,
            hide_mixed_script_variants=False
        )

        response = []
        for (v_label, v_disposition, _, _, _, _) in variant_labels:
            v_ulabel = "".join(map(chr, v_label))

            try:
                v_alabel = idna.encode(v_ulabel).decode(LGRServer.charset)

            except:
                v_alabel = None

            if (v_alabel and v_alabel != a_label):
                response.append({
                    "u_label":      v_ulabel,
                    "a_label":      v_alabel,
                    "code_points":  v_label,
                    "disposition":  v_disposition,
                })

        return self.respond(200, json.dumps(response))

if __name__ == "__main__":
    LGRServer.run()
