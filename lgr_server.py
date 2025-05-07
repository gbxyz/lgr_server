#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import os
import json
import idna
from lgr.parser.xml_parser import XMLParser
from munidata import UnicodeDataVersionManager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from pprint import pprint
from glob import glob
import subprocess

class LGRServer(BaseHTTPRequestHandler):
    charset = "utf-8"
    unimanager = UnicodeDataVersionManager()
    lgr_dir = os.path.dirname(__file__) + "/lgrs/"
    lgrs = {}

    def do_GET(self):
        segments = urlparse(self.path).path[1:].split("/")
        tag = segments[0]
        a_label = segments[1]

        lgr = self.get_lgr(tag)

        if lgr is None:
            self.send_response(400)
            self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(bytes(json.dumps({
                "error": 400,
                "message": "Invalid tag '{}'".format(tag),
            }, indent=2), LGRServer.charset))
            return

        code_points = tuple([ord(c) for c in idna.decode(a_label)])

        (eligibility, _, invalid_code_points, disposition, _, _) = lgr.test_label_eligible(code_points, is_variant=False, collect_log=False)

        variant_labels = lgr.compute_label_disposition(code_points, include_invalid=True, hide_mixed_script_variants=False)

        response = {
            'a_label': a_label,
            'tag': tag,
            'u_label': "".join(map(chr, code_points)),
            'code_points': code_points,
            'invalid_code_points': list(map(lambda cp: cp[0], invalid_code_points)),
            'eligibility': eligibility,
            'disposition': disposition,
        }

        if (eligibility):
            response['index_label'] = "".join(map(chr, lgr.generate_index_label(code_points)))
            response['variants'] = []
            for (v_label, v_disposition, _, _, _, _) in variant_labels:
                v_ulabel = "".join(map(chr, v_label))
                v_alabel = idna.encode(v_ulabel).decode(LGRServer.charset)
                if (v_alabel != a_label):
                    response['variants'].append({
                        'a_label': v_alabel,
                        'code_points': v_label,
                        'u_label': v_ulabel,
                        'disposition': v_disposition,
                    })

        self.send_response(200)
        self.send_header("content-type", "application/json; charset={}".format(LGRServer.charset))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(bytes(json.dumps(response, indent=2), LGRServer.charset))

    def _get_lgr_filename(self, tag):
        return LGRServer.lgr_dir + tag + ".xml"

    def get_lgr(self, tag):
        if not hasattr(LGRServer.lgrs, tag):
            try:
                parser = XMLParser(self._get_lgr_filename(tag))
                parser.unicode_database = LGRServer.unimanager.register(None, LGRServer.icu_libpath, LGRServer.icu_i18n_libpath, LGRServer.icu_libver)
                LGRServer.lgrs[tag] = parser.parse_document()
            except:
                LGRServer.lgrs[tag] = None

        return LGRServer.lgrs[tag]

if __name__ == "__main__":
    os.putenv("PKG_CONFIG_PATH", "/opt/homebrew/opt/icu4c@75/lib/pkgconfig")

    try:
        output = subprocess.check_output(["pkg-config", "--modversion", "icu-uc"]).decode("utf-8").strip()
        LGRServer.icu_libver = int(float(output))

        output = subprocess.check_output(["pkg-config", "--libs", "icu-uc"]).decode("utf-8").strip()
        libdir = re.match(r"-L([^ ]+)", output).group(1)

        files = {}
        for f in glob(libdir + "/*"):
            match = re.match(r"^lib(icuuc|icui18n).\d+\.(dylib|so)$", os.path.basename(f))
            if match is not None:
                files[match.group(1)] = match.group(0)

        LGRServer.icu_libpath = libdir + "/" + files["icuuc"]

        LGRServer.icu_i18n_libpath = libdir + "/" + files["icui18n"]

    except:
        print("Unable to determine ICU lib version using pkg-config")
        exit(1)

    server = HTTPServer(server_address=("0.0.0.0", 8080), RequestHandlerClass=LGRServer)

    print("Server running on http://0.0.0.0:8080")

    server.serve_forever()
