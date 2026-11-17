# Documentation index

**Read these as web pages, with search and diagrams: https://www.mhraaga.in/docs/index.html**
The pages are built from the Markdown here: `python3 tools/build_docs.py` (needs `pip install markdown pygments`; see the header of that file for the diagram step), then deploy.

Start with the [root README](../README.md), then:

| Doc | For |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The detailed architecture, step by step, and how Kalkee is (and is not) used |
| [SINGER.md](SINGER.md) | The singer layer: make the raga song SING with YuE2, free on Colab |
| [FILES.md](FILES.md) | **Every music file and what it holds** |
| [THIRD_PARTY.md](THIRD_PARTY.md) | Vendored upstream repos (YuE2, Bark, setup-ffmpeg and more), licences, how to update them |
| [kalkee/PLATFORM.md](kalkee/PLATFORM.md) | **KALKEE**, the platform: full form, the six parts, many agents, one outcome |
| [kalkee/README.md](kalkee/README.md) | Kalkee in mhRaaga: the music agents, how they learn |
| [ENGINE.md](ENGINE.md) | Every engine module: compose, ragas, tala, brief, poems, lyrics, physics, GAN, auto-tune |
| [BACKEND.md](BACKEND.md) | handler, studio, team, voice, admin, the tables and the infrastructure |
| [ADMIN.md](ADMIN.md) | The admin dashboard: users, types, columns, cloud cost |
| [API.md](API.md) | Developers who call the API from outside (accounts, endpoints, the score format) |
| [../tool_layer_mhraga/mhraaga-cloud/web/developers.html](../tool_layer_mhraga/mhraaga-cloud/web/developers.html) | The architecture page, published at https://www.mhraaga.in/developers.html |
| [SOUND.md](SOUND.md) | How the instruments are modelled and why it should sound natural, with the measurements |
| [VOICE.md](VOICE.md) | The neural voice, costs and caps |
| [TEAM_AND_PHYSICS.md](TEAM_AND_PHYSICS.md) | Shared studio, Box2D physics, auto-tune, GAN phrases |
| [STUDIO.md](STUDIO.md) | Stories, pravachan, people, rules |
| [AGENTIC_ARCHITECTURE.md](AGENTIC_ARCHITECTURE.md) | The song factory (agents and critics) |
| [DOMAIN.md](DOMAIN.md) | Domain, DNS and HTTPS |
| [components/android-app.md](components/android-app.md) | The Flutter Android app |

