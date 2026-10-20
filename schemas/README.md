# JSON contracts

`decision.schema.json` describes the model's entire allowed output. Python
`Decision.parse` enforces it plus string-size, duplicate-field and action/view rules.
The model's identifiers/timestamps are not accepted.

`observation.schema.json` describes `Observation.envelope(image_file)`, the
recorded JSON metadata alongside the saved JPEG. It preserves separate sensor
and host receipt clocks, ordinary telemetry, allowed actions and the trusted
request/episode/frame IDs. JPEG bytes stay in the `Frame` object and local evidence
file; the llama adapter transmits them as image content.

`mission.schema.json` gives the core shape of the configuration; Python
`validate_mission` additionally checks finite limits, flight volume, connected
route edges, and the physical-operation prohibition before executor construction.
`event.schema.json` defines the event-stream base fields; event-specific fields
are additive.
