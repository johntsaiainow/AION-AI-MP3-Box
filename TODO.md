# AION Embedded Linux — TODO

Project: AI-NOW TECHNOLOGY, INC.
Repository: AI-Now-Inc/ai-now-yocto-rpi3
Platform: Raspberry Pi 3 ARM64
Yocto: Scarthgap 5.0 LTS

## P0 — Build Reproducibility

- [ ] Create build-aion.sh for automated Yocto environment setup.
- [ ] Document required host dependencies.
- [ ] Pin Poky, meta-raspberrypi and meta-openembedded revisions.
- [ ] Provide reproducible local.conf and bblayers.conf templates.
- [ ] Verify clean builds from a fresh Git clone.
- [ ] Remove machine-specific absolute paths from build instructions.
- [ ] Validate all custom BitBake recipes and dependencies.

## P1 — Hardware Validation

- [ ] Document Raspberry Pi 3 hardware test procedures.
- [ ] Verify kmscon UTF-8/CJK display on tty1.
- [ ] Verify getty recovery console on tty2.
- [ ] Verify NetworkManager Wi-Fi connectivity.
- [ ] Verify OpenSSH remote login.
- [ ] Verify Avahi/mDNS discovery using `aiy-box-rebirth.local`.
- [ ] Verify systemd service startup and recovery.
- [ ] Validate SD card flashing scripts and device safeguards.
- [ ] Record boot logs and hardware test results.

## P2 — Release v0.1.0

- [ ] Complete reproducible build validation.
- [ ] Create CHANGELOG.md.
- [ ] Generate release image and SHA256SUMS.
- [ ] Review image contents for secrets and credentials.
- [ ] Document SD card flashing and first boot.
- [ ] Create GitHub Release v0.1.0.
- [ ] Attach validated image artifacts when appropriate.

## P3 — Documentation

- [ ] Expand README.md with complete build instructions.
- [ ] Document Yocto layer architecture.
- [ ] Add troubleshooting documentation.
- [ ] Add supported hardware matrix.
- [ ] Document contribution guidelines.

## Security and Repository Administration

- [ ] Enable GitHub two-factor authentication before 2026-12-12.
- [ ] Review repository access permissions.
- [ ] Confirm the intended long-term repository owner.
- [ ] Review source files for embedded secrets before releases.

## Future Development

- [ ] Evaluate offline Vosk speech recognition.
- [ ] Evaluate Piper text-to-speech on Raspberry Pi 3.
- [ ] Investigate AION voice assistant integration.

---

AION Embedded Linux
AI-NOW TECHNOLOGY, INC.
