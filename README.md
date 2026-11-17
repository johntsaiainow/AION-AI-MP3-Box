# AION AI MP3 Box

### An Open-Source, Offline AI-Powered Music Player

**AION AI MP3 Box** is an embedded Linux project that transforms a
Raspberry Pi into an intelligent, voice-controlled music player.

Built on **AION Embedded Linux**, a custom Yocto Project distribution,
the system combines traditional MP3 playback with offline speech
recognition, text-to-speech, and intelligent voice interaction.

The project explores how modern AI technologies can be integrated
into compact, resource-constrained embedded systems without requiring
continuous cloud connectivity.

## Project Goals

- Build a standalone AI-powered MP3 player.
- Support offline music playback and voice control.
- Integrate Google AIY Voice Kit hardware.
- Provide multilingual speech interaction.
- Run on a custom Yocto-based Linux distribution.
- Minimize cloud dependencies.
- Develop a modular, extensible embedded AI platform.

## Hardware Platform

Primary hardware:

- Raspberry Pi 3
- Google AIY Voice Kit
- AIY Voice HAT or Voice Bonnet, depending on hardware revision
- Microphone and speaker
- MicroSD storage
- Physical button and LED

Additional peripherals may be supported in future releases.

## Software Architecture

    +----------------------------------+
    |         AION AI MP3 Box          |
    +----------------------------------+
    |        Voice Command Layer       |
    |         Vosk Offline STT         |
    +----------------------------------+
    |       Music Control Engine       |
    |         MPD / mpg123             |
    +----------------------------------+
    |      Speech Output Engine        |
    |       Piper / eSpeak NG          |
    +----------------------------------+
    |         ALSA Audio Layer         |
    +----------------------------------+
    |        AION Embedded Linux       |
    |       Yocto Scarthgap ARM64      |
    +----------------------------------+
    |         Raspberry Pi 3           |
    |       Google AIY Voice Kit       |
    +----------------------------------+

The components above represent the planned architecture.
Integration and hardware validation are ongoing.

## AION Embedded Linux

AION AI MP3 Box is based on AION Embedded Linux, a custom
Linux distribution developed using the Yocto Project.

The base system provides:

- ARM64 Raspberry Pi support
- systemd service management
- OpenSSH remote access
- NetworkManager Wi-Fi management
- Avahi/mDNS network discovery
- UTF-8 and CJK console support
- kmscon framebuffer terminal

Upstream project:

https://github.com/AI-Now-Inc/ai-now-yocto-rpi3

## Google AIY Voice Kit Integration

Google AIY Voice Kit provides an integrated hardware platform
for voice-enabled embedded applications.

The project aims to support:

- Microphone audio capture
- Speaker audio playback
- Physical button interaction
- LED status indication
- ALSA audio integration
- Device Tree and kernel driver configuration

Compatibility depends on the specific AIY hardware revision.

## Offline Speech Recognition

Vosk is the proposed speech recognition engine.

Planned voice commands include:

- Play music
- Pause music
- Stop playback
- Next track
- Previous track
- Volume up
- Volume down
- Play a selected artist or album

Speech recognition will be designed to operate locally.

## Text-to-Speech

The project will evaluate two offline speech engines:

**Piper**

Neural text-to-speech for natural-sounding voice responses.

**eSpeak NG**

Lightweight speech synthesis for resource-constrained systems.

The final engine selection will depend on performance,
memory usage, and Raspberry Pi 3 compatibility.

## Music Playback

The planned music subsystem includes:

- MP3 playback
- Local music library indexing
- Playlist management
- Album and artist selection
- Hardware button controls
- Voice-based playback commands

MPD and mpg123 will be evaluated as playback backends.

## Development Roadmap

### Phase 001 - Platform Preparation

- [x] Clone AION Embedded Linux source repository
- [ ] Identify AIY Voice Kit hardware revision
- [ ] Verify Yocto build environment
- [ ] Create dedicated AI MP3 Box image recipe

### Phase 002 - Audio Hardware

- [ ] Configure ALSA
- [ ] Integrate AIY audio drivers
- [ ] Test speaker playback
- [ ] Test microphone recording
- [ ] Validate physical button and LED

### Phase 003 - Music Player

- [ ] Integrate MPD or mpg123
- [ ] Implement local music library
- [ ] Implement playback controls
- [ ] Configure automatic startup

### Phase 004 - Offline Voice Recognition

- [ ] Integrate Vosk
- [ ] Evaluate small-footprint speech models
- [ ] Implement voice command recognition
- [ ] Connect speech commands to playback controls

### Phase 005 - Speech Synthesis

- [ ] Integrate eSpeak NG
- [ ] Evaluate Piper
- [ ] Implement spoken system responses
- [ ] Support multilingual voice interaction

### Phase 006 - System Integration

- [ ] Create systemd services
- [ ] Optimize memory and CPU usage
- [ ] Validate offline operation
- [ ] Perform Raspberry Pi 3 hardware testing
- [ ] Prepare first experimental release

## Development Environment

Host operating system: Linux

Build system: Yocto Project / BitBake

Target architecture: ARM64

Target platform: Raspberry Pi 3

Primary implementation languages:

- Python
- C / C++
- Shell scripting
- BitBake

## Project Status

**Early Development / Experimental**

The AION Embedded Linux foundation has been developed and
tested separately. AI MP3 Box audio integration, speech
recognition, and text-to-speech remain under development.

## Credits

Developed as part of the AION embedded AI ecosystem.

AI-NOW TECHNOLOGY, INC.

## License

The project contains components with their own upstream licenses.
Licensing of new project-specific software will be documented
before the first release.
