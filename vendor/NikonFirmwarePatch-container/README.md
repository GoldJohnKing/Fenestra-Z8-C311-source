# Local container-tool dependency

Reviewed dependency sources from NikonFirmwarePatch-v0.3.0-r1:

- `z8prores/package.py`: SHA-256 `2f24ea0214ca7e8bae044f91a4ba2980bc4e6471bb47b75d5afe1bdfcc42cd29`
- `resources/input.json`: original firmware identity used by that reader/writer
- `LICENSE` and `NOTICE.md`: original licensing and provenance

This is a separate dependency under its original GPL terms. It is not relicensed under Fenestra's license. The reviewed source bytes remain unchanged and the Fenestra adapter still verifies their pinned SHA-256 before execution.

Pass this directory explicitly as `--external-project vendor/NikonFirmwarePatch-container`. The card WAV sources are a separate GPL dependency. See their LICENSE and NOTICE.
