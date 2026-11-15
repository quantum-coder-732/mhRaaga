# Vendored upstream repos (`third_party/`)

Five public repositories are vendored: their code is copied into `third_party/` and committed in this repo, unchanged, so a plain `git clone` has everything. `third_party/UPSTREAM` records each upstream URL and the exact commit we have; `tools/update_third_party.sh` compares it with upstream and, with `--apply`, copies the newer code in.

| Repo | Licence | Used? | How |
|---|---|---|---|
| [multimodal-art-projection/YuE](https://github.com/multimodal-art-projection/YuE) (YuE2) | Code Apache-2.0. **Weights: CC BY-NC 4.0 plus creator permission** | **Yes, optional** | The singer layer ([SINGER.md](SINGER.md)): the raga melody becomes a score the model sings. Free on a Colab GPU with `singer/colab_singer.ipynb`; or a paid GPU machine with `gpu-worker/worker.py`. |
| [suno-ai/setup-ffmpeg](https://github.com/suno-ai/setup-ffmpeg) | MIT | **Yes** | `.github/workflows/ci.yml` runs it as a local action (`uses: ./third_party/setup-ffmpeg`) to install ffmpeg in CI. |
| [suno-ai/bark](https://github.com/suno-ai/bark) | MIT | Reference only | A text-to-audio model. Not wired in: the AI voice already uses a hosted model that handles the Indian languages, and Bark needs a GPU and several GB of weights. Kept so it can be tried on the GPU machine. |
| [suno-ai/CreateAPI](https://github.com/suno-ai/CreateAPI) | MIT | Reference only | Generates Swift API clients from OpenAPI. mhRaaga has no iOS app and no OpenAPI file yet. |
| [suno-ai/quadfeather](https://github.com/suno-ai/quadfeather) | see its folder | Reference only | A tool for tiling very large scatter plots. Nothing in mhRaaga needs it. |

## YuE2 licence in plain words
The code is Apache-2.0. The **model weights** are free for personal users, creators and musicians (including monetising what you make), and for non-commercial research and education. **A company using it commercially needs a licence from the authors.** Decide this before you offer the AI singer to the public. It is therefore limited to administrators for now.

## Keeping them current
```bash
tools/update_third_party.sh            # shows which repos have new commits upstream
tools/update_third_party.sh --apply    # moves the pointers to the newest commits, then review, test, commit
```
A weekly GitHub Action (`.github/workflows/third-party-updates.yml`) does the check and opens a pull request when something moved.

## Forks
These are copies of the **upstream** repositories. To track your own fork (for example to patch Bark), fork it on GitHub and change its URL in `third_party/UPSTREAM`.
