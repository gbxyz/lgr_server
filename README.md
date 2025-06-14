# LGR Server

LGR Server provides a simple API to validate domain name labels against the [Label Generation Rulesets (LGRs)](https://www.rfc-editor.org/rfc/rfc8228.html).

Using this API, a domain name registry or registrar can:

1. determine whether a given label is valid against a particular LGR; and
2. determine if what variants (if any) the label has, and their disposition (blocked or allocatable).

## Live demo

A live demo of the server is available at <https://lgr.gavinbrown.xyz>.

## API details

### OpenAPI description

* [YAML](openapi.yaml) ([view in Swagger Editor](https://editor-next.swagger.io/?url=https://raw.githubusercontent.com/gbxyz/lgr_server/refs/heads/main/openapi.yaml))

### Label validation

```
# curl -s http://localhost:8080/root-zone/und-Latn/xn--caf-dma | jq .
{
  "u_label": "café",
  "a_label": "xn--caf-dma",
  "code_points": [
    99,
    97,
    102,
    233
  ],
  "tag": "und-Latn",
  "invalid_code_points": [],
  "eligible": true,
  "disposition": "valid",
  "index_label": "xn--caf-dma",
  "is_index_label": true,
  "approx_variants": 4
}
```

A `GET` request of the form `/{set}/{table}/{label}` will return a JSON object with the structure above. `{set}` refers to the specific [LGR set](lgrs/), while `{table}` must correspond to a [language tag](https://datatracker.ietf.org/doc/html/rfc5646) and maps to a file in the chosen LGR set. `{label}` is the domain name label (e.g. `example`) in either A-label or U-label format.

* `u_label` - the "U-label" representation of the label in UTF-8
* `a_label` - the "A-label" representation of the label in Punycode
* `code_points` - an array of Unicode code points represented as decimal integers
* `tag` - the language (or script) tag
* `invalid_code_points` - those code points in the label that are not valid for the LGR
* `eligible` - a boolean indicating whether the label is allocatable
* `disposition` - one of `valid`, `invalid`, `blocked` or `allocatable`
* `index_label` - the "index" of the set of variant labels to which the given label belongs
* `is_index_label` - a boolean indicating whether the provided label is identical to the index label
* `approx_variants` - the estimated number of variant labels. Some labels can generate geometrically large numbers of variants, so this provides a hint on the likely size of the response to a `/{table}/{label}/variants` request (see below)

### Getting variants

```
$ curl -s http://localhost:8080/root-zone/und-Latn/xn--caf-dma/variants | jq .
[
  {
    "u_label": "caƒé",
    "a_label": "xn--ca-cja98d",
    "code_points": [
      99,
      97,
      402,
      233
    ],
    "disposition": "blocked"
  },
  {
    "u_label": "cáfé",
    "a_label": "xn--cf-mia7a",
    "code_points": [
      99,
      225,
      102,
      233
    ],
    "disposition": "blocked"
  },
  {
    "u_label": "cáƒé",
    "a_label": "xn--c-ufay98d",
    "code_points": [
      99,
      225,
      402,
      233
    ],
    "disposition": "blocked"
  }
]
```

A `GET` request of the form `/{set}/{table}/{label}/variants` will return a JSON array of objects, each of which represents a variant of `{label}`. Each object has `u_label`, `a_label`, `code_points` and `disposition` properties, whose semantics are the same as above.

### Checking if one label is a variant of another

A `GET` request of the form `/{set}/{table}/{label}/{variant}` will return a boolean JSON value (ie `true` or `false`) indicating whether `{variant}` is a variant of `{label}`.

## LGR Sets

LGR Server comes bundled with three sets of LGRs:

* [`root-zone`](lgrs/root-zone) ([more info](https://www.icann.org/resources/pages/root-zone-lgr-2015-06-21-en))
* [`second-level-reference`](lgrs/second-level-reference) ([more info](https://www.icann.org/en/contracted-parties/registry-operators/second-level-reference-label-generation-rules-21-06-2015-en))
* [`full-variant-set`](lgrs/full-variant-set) ([more info](https://newgtldprogram.icann.org/en/application-rounds/round2/rsp/full-variant-set-lgrs))

## Starting the server

Use `docker compose up`. This will expose the server on port 8080.

Also:

```
$ docker run -p 8080:8080 gbxyz/lgr_server:latest
```

## Implementation

LGR Server is written in Python, so it can make use of the ICANN [lgr-core](https://github.com/icann/lgr-core) library. This is my first serious piece of Python programming so please be gentle :)

## Performance

The time taken to answer `GET /{set}/{table}/{label}` requests depends on the LGR set, on my development machine, the typical RTTs are:

* `root-zone`: 100ms
* `second-level-reference`: 70ms
* `full-variant-set`: 200ms

The time taken to answer `GET /{set}/{table}/{label}/variants` increases geometrically with the length of `{label}`, so the time required to compute the variants of `foo` is about 4 times longer than the time required for `fo`, and for `foobar` it's about 30 times longer. So caution should be exercised when making these requests in-band, especially using user-provided (or attacker-provided) values for `{label}`.

## License

See [LICENSE](LICENSE).
