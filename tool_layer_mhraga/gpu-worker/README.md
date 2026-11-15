# AI singer worker (YuE2)

Makes real sung songs from lyrics and a style. The model is **YuE2** (`third_party/YuE`, code Apache-2.0).
**Weights licence:** free for personal users, creators and musicians (outputs may be monetised); free for non-commercial research and education; **companies need a commercial licence from the authors** (see `third_party/YuE/README.md`, "License"). Check this before using it for a business.

**Free first:** if you do not want to spend money, use the Colab notebook instead (`tool_layer_mhraga/singer/colab_singer.ipynb`, see docs/SINGER.md). This worker is for a GPU machine you decide to pay for.

## What you need
A Linux machine with an NVIDIA GPU that supports BF16 and has **24 GB of memory** (for example an AWS `g5.xlarge`, an A10G, around one US dollar an hour on demand; spot is cheaper). Python 3.12, ffmpeg, and an instance role (or keys) that can use the `mhraaga-songs` table and write `yue/*` in the site bucket.

## Set up
```bash
git clone --recurse-submodules https://github.com/quantum-coder-732/mhRaaga.git && cd mhRaaga
python3.12 -m venv .venv && . .venv/bin/activate
pip install ./third_party/YuE boto3          # the first song downloads the model from Hugging Face
export SITE_BUCKET=mhraaga-site-877157050453-ap-south-1 AWS_REGION=ap-south-1
python tool_layer_mhraga/gpu-worker/worker.py --fake --once     # no GPU: checks the queue and the upload
python tool_layer_mhraga/gpu-worker/worker.py                   # the real thing
```
Switch the queue on in the stack: deploy with parameter `GpuEngine=on`. Then open **Admin > AI singer** and submit a style and lyrics. The page shows when a worker is alive. The worker stops the machine itself after 15 idle minutes (`IDLE_STOP_SECONDS`, 0 turns that off). **Check that the instance is stopped**; an idle GPU still costs money.

## Honest limits
The worker has not been run on a real GPU yet (none was available when it was written); `--fake` proves the queue, claim, MP3 conversion and upload. A song takes minutes. YuE2 sings in the languages it was trained on; check Hindi, Marathi and the other Indian languages by ear before relying on it.
