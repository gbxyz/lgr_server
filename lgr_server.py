#!/usr/bin/env python
# -*- coding: utf-8 -*-

from argparse import ArgumentParser
import os
import pkgconfig
import json
import idna
import subprocess
import picu
import re
from lgr.parser.xml_parser import XMLParser
import munidata
from munidata import UnicodeDataVersionManager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote
from urllib.parse import urlparse
from pprint import pprint

class LGRServer(BaseHTTPRequestHandler):

    charset     = "utf-8"
    unimanager  = UnicodeDataVersionManager()
    lgr_dir     = "{}/lgrs/second-level-reference".format(os.path.abspath(os.path.dirname(__file__)))
    lgrs        = {}

    def run():
        p = ArgumentParser("LGR Server", " A simple REST API for accessing Label Generation Rulesets (LGRS)")
        p.add_argument("--lgr-set", choices=["root-zone", "full-variant-set", "second-level-reference"])

        args = p.parse_args()

        LGRServer.icu_libver = int(float(pkgconfig.modversion("icu-uc")))

        if str(LGRServer.icu_libver) not in picu.loader.KNOWN_ICU_VERSIONS:
            print("Note: monkey patching picu.loader.KNOWN_ICU_VERSIONS")
            picu.loader.KNOWN_ICU_VERSIONS = picu.loader.KNOWN_ICU_VERSIONS + (str(LGRServer.icu_libver),)

        if not hasattr(munidata.idna.idnatables.IDNA_UNICODE_MAPPING, "15.0.0"):
            print("Note: monkey patching munidata.idna.idnatables.IDNA_UNICODE_MAPPING")
            munidata.idna.idnatables.IDNA_UNICODE_MAPPING["15.0.0"] = munidata.idna.idnatables.IDNA_UNICODE_MAPPING["12.1.0"]

        libs = {}
        for path in subprocess.check_output(["find", "/usr/lib", "-regextype", "sed", "-iregex", ".*/libicu\\(uc\\|i18n\\).so.{0}".format(LGRServer.icu_libver)]).decode(LGRServer.charset).strip().split("\n"):
            libs[os.path.splitext(os.path.basename(path))[0]] = path

        LGRServer.icu_libpath = libs["libicuuc.so"]
        LGRServer.icu_i18n_libpath = libs["libicui18n.so"]

        if hasattr(args, "lgr_set") and args.lgr_set is not None:
            LGRServer.lgr_dir = "{0}/lgrs/{1}".format(os.path.abspath(os.path.dirname(__file__)), args.lgr_set)

        server = HTTPServer(server_address=("0.0.0.0", 8080), RequestHandlerClass=LGRServer)

        print("Server running on http://0.0.0.0:8080")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            exit()

    def do_GET(self):
        segments = unquote(urlparse(self.path).path[1:], LGRServer.charset).split("/")

        if (len(segments) < 2 or len(segments) > 3):
            self.send_response(400)
            self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(bytes(json.dumps({
                "error": 400,
                "message": "Invalid path '{}'".format(self.path),
            }, indent=2), LGRServer.charset))
            return

        tag = segments[0]

        if re.match("^xn--", segments[1], re.IGNORECASE):
            a_label = segments[1]
        else:
            a_label = idna.encode(segments[1]).decode(LGRServer.charset)

        lgr = self.get_lgr(tag)

        if lgr is None:
            self.send_response(400)
            self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(bytes(json.dumps({
                "error": 404,
                "message": "Unknown tag '{}'".format(tag),
            }, indent=2), LGRServer.charset))
            return

        code_points = tuple([ord(c) for c in idna.decode(a_label)])

        (eligible, _, invalid_code_points, disposition, _, _) = lgr.test_label_eligible(code_points, is_variant=False, collect_log=False)

        if 2 == len(segments):
            try:
                index_label = "".join(map(chr, lgr.generate_index_label(code_points)))
                approx_variants = lgr.estimate_variant_number(code_points)
            except:
                index_label = None
                approx_variants = 0

            response = {
                "u_label":              "".join(map(chr, code_points)),
                "a_label":              a_label,
                "code_points":          code_points,
                "tag":                  tag,
                "invalid_code_points":  list(map(lambda cp: cp[0], invalid_code_points)),
                "eligible":             eligible,
                "disposition":          disposition,
                "index_label":          index_label,
                "approx_variants":      approx_variants,
            }

        elif "variants" != segments[2]:
            self.send_response(400)
            self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(bytes(json.dumps({
                "error": 400,
                "message": "Invalid path '{}'".format(self.path),
            }, indent=2), LGRServer.charset))
            return

        else:
            if not eligible:
                self.send_response(404)
                self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
                self.send_header("access-control-allow-origin", "*")
                self.end_headers()
                self.wfile.write(bytes(json.dumps({
                    "error": 400,
                    "message": "Invalid label '{}'".format(a_label),
                }, indent=2), LGRServer.charset))
                return

            variant_labels = lgr.compute_label_disposition(code_points, include_invalid=True, hide_mixed_script_variants=False)

            response = []
            for (v_label, v_disposition, _, _, _, _) in variant_labels:
                v_ulabel = "".join(map(chr, v_label))
                v_alabel = idna.encode(v_ulabel).decode(LGRServer.charset)

                if (v_alabel != a_label):
                    response.append({
                        "u_label":      v_ulabel,
                        "a_label":      v_alabel,
                        "code_points":  v_label,
                        "disposition":  v_disposition,
                    })

        self.send_response(200)
        self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(bytes(json.dumps(response, indent=2), LGRServer.charset))

    def _get_lgr_filename(self, tag):
        return "{0}/{1}.xml".format(LGRServer.lgr_dir, tag)

    def get_lgr(self, tag):
        if not hasattr(LGRServer.lgrs, tag):
            LGRServer.lgrs[tag] = None

            file = self._get_lgr_filename(tag);
            if os.path.exists(file):
                parser = XMLParser(file)
                parser.unicode_database = LGRServer.unimanager.register(None, LGRServer.icu_libpath, LGRServer.icu_i18n_libpath, LGRServer.icu_libver)

                LGRServer.lgrs[tag] = parser.parse_document()

        return LGRServer.lgrs[tag]

if __name__ == "__main__":
    LGRServer.run()
