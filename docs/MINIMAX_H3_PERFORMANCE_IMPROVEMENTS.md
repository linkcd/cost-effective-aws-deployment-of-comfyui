# MiniMax H3 ComfyUI Performance Investigation

Investigation date: 2026-09-03
AWS Region: `ap-northeast-1`
Purpose: Preserve the measured baseline, findings, and improvement options for testing one at a time.

## Executive summary

The investigated MiniMax H3 image-to-video run took exactly **617.969 seconds (10:17.97)**.

The run was slow for three separate reasons:

1. Approximately 44.3 GB of models were read from a gp3 volume limited to 125 MiB/s.
2. The workflow used the full 20-step path while the installed Turbo LoRA was disabled.
3. The selected `int8_convrot` model was running with PyTorch cu126, while the official model guidance recommends cu130 for that format.

The GPU itself was fully utilized during denoising. Increasing CPU capacity alone will not materially improve the 10.96-second sampling-step time.

The recommended order is:

1. Establish cold and warm benchmarks.
2. Enable the Turbo workflow with the correct settings.
3. Rebuild the container for CUDA/PyTorch cu130.
4. Move frequently used H3 models to local NVMe or increase gp3 throughput.
5. Consider a G7e GPU only after the software and storage changes are measured.

## Selected H3-specific software stack

The container is now pinned to the following stable test configuration:

| Component | Selected version |
|---|---|
| NVIDIA CUDA runtime image | `13.0.3-runtime-ubuntu22.04` |
| PyTorch | `2.14.0+cu130` |
| TorchVision | `0.29.0+cu130` |
| TorchAudio | `2.11.0+cu130` |
| Triton | `3.8.0` through the PyTorch dependency |
| Comfy Kitchen | `0.2.31` through the pinned ComfyUI requirements |
| ComfyUI | Commit `3216c62e9962c3babd28a4dfea6e5aef50b8fe16` |
| ComfyUI Manager | Commit `b75fc664ecab9c4602380d9660833d02f6a63333` |

Why this combination was selected:

- The official H3 model card prefers `int8_convrot` with PyTorch cu130.
- PyTorch 2.14.0 is a stable release and the live cu126 container already ran
  successfully with the same Torch/TorchVision/TorchAudio version family.
- The official cu130 indexes provide Torch 2.14.0 and TorchVision 0.29.0.
  TorchAudio 2.11.0 is currently the newest Linux cu130 wheel and its metadata
  does not constrain the installed Torch version.
- PyTorch's cu130 dependency metadata selects CUDA toolkit package 13.0.3, and
  NVIDIA publishes a matching CUDA 13.0.3 runtime image.
- The live ComfyUI commit is retained for the first A/B benchmark. The fifteen
  newer upstream commits inspected did not contain a demonstrated local H3
  FL2VA inference-speed fix.
- ComfyUI's pinned Comfy Kitchen 0.2.31 is retained. The newer 0.2.32 release
  does not provide a demonstrated speed improvement for this H3 FL2VA path.

The image intentionally does not include the open H3 audio-VAE or per-step
host-synchronization pull requests. Those remain separate experiments after the
stable runtime and cache have been measured.

## Implemented NVMe cache behavior

The cache is enabled by default without changing the gp3 volume's performance
settings.

- Host bootstrap detects the EC2 instance-store NVMe device, formats it as
  ext4 when empty, mounts it at `/mnt/comfy-cache`, and writes a marker file.
- ECS maps that host path into the ComfyUI container.
- The persistent EBS volume remains mounted at
  `/home/user/opt/ComfyUI`.
- Normal ComfyUI and Manager downloads continue to use the default EBS model
  directories.
- On task startup, only files listed in
  `h3_model_cache_manifest.json` are moved into the canonical EBS H3 store and
  copied atomically to NVMe.
- ComfyUI reads the NVMe path first and the EBS store second.
- Models not listed in the manifest remain in their normal EBS directory and
  are never cached.
- Replacing a manifest-managed model through ComfyUI puts the new download on
  EBS first. On the next task start, the old EBS source is archived, the new
  EBS file becomes canonical, and the NVMe copy is refreshed.
- A missing NVMe device, mount marker, full cache disk, or copy error falls
  back to EBS without preventing ComfyUI startup.

For the live deployment, the CDK configuration preserves REX-Ray volume
`ComfyUIVolume-8a39c00b32-20260901154923` and pins the replacement host to
subnet `subnet-0f26675ddc32e0174` in the EBS volume's Availability Zone. This
allows the new host to rebuild disposable NVMe data from the existing EBS
contents.

## Live image-only rollout verification (2026-09-03)

The validated image was deployed directly to ECS without applying the CDK
network, ASG, volume, or mount changes.

| Item | Verified result |
|---|---|
| ECS task definition | `ComfyUIStackEcsConstructEcsConstructComfyTaskDef7CE06D12:6` |
| ECS deployment | Completed and reached steady state |
| Container health | Healthy |
| Load-balancer target | Healthy on port 8181 |
| Image digest | `sha256:cc27eeda4e146bac6468f7b89b826d577bbae4d1e165bfae0331384104070d7f` |
| Runtime | PyTorch `2.14.0+cu130`, CUDA 13.0, Triton 3.8.0 |
| Comfy Kitchen | 0.2.31; optimized CUDA backend available and enabled |
| Persistent volume | Existing `vol-05e007e7a67e9e7a0`, 5,000 GiB gp3 |
| gp3 settings | Unchanged at 3,000 IOPS and 125 MiB/s |
| H3 EBS model store | Five manifest files available; one optional manifest file missing |
| Cache selection | `cache_ready=false`; startup explicitly selected the EBS fallback |
| First cu130/EBS generation | 374.60 seconds; successful video |
| Attempted warm generation | 377.66 seconds, but it ran in a replacement ECS task and was another cold run |
| EBS reads during second run | 44,523,508,736 bytes; throughput remained near the 125 MiB/s gp3 limit |
| Post-generation stability | Original task exited 137 with `OutOfMemoryError` and ECS replaced it |

This proves that the new image and cache-aware startup code work with the
existing persistent EBS contents. Because this was intentionally an image-only
deployment, `/mnt/comfy-cache` is not mounted and the local NVMe acceleration
is not active yet. The current task reads the managed H3 files from
`/home/user/opt/ComfyUI/model_store/h3` on EBS. Activating NVMe later requires
only the host bootstrap and ECS mount mapping; it does not require a VPC
networking change.

The attempted warm benchmark was not actually warm. Immediately after the
first output completed, the 64 GiB host OOM-killed ComfyUI. The replacement
task then reread approximately 44.52 GB from EBS and produced a second cold
result of 377.66 seconds. During that run, the dominant phases were:

- Approximately 114 seconds around text-encoder loading and conditioning.
- 163.00 seconds of diffusion-model initialization.
- Approximately 30 seconds for all eight denoising steps.
- Approximately 44 seconds for audio/video VAE decoding and output.

The deployed ComfyUI revision enabled approximately 47,046 MiB of pinned host
memory. It supports both `--disable-pinned-memory` and `--fast-disk`; the latter
prefers disk-backed Dynamic VRAM loading when fast NVMe storage is available.
The next controlled test should combine the local NVMe cache with a host-memory
mitigation so that the process survives long enough to measure a true warm run.

## Measured baseline

### Deployment

| Component | Observed configuration |
|---|---|
| EC2 instance | `g6e.2xlarge` |
| GPU | One NVIDIA L40S |
| Usable GPU memory | Approximately 45,458 MiB |
| Host memory | Approximately 63,430 MiB |
| ComfyUI | 0.34.0 |
| Container CUDA base | CUDA 12.9 |
| PyTorch | `2.14.0+cu126` |
| Persistent model volume | 5,000 GiB gp3 |
| gp3 performance | 3,000 IOPS and 125 MiB/s |
| Local instance NVMe | Approximately 450 GB, present but unused |

### Workflow

| Setting | Observed value |
|---|---|
| Mode | MiniMax H3 FL2VA image-to-video |
| Duration | 5 seconds |
| Frame rate | 24 fps |
| Generated frames | 124 |
| Resolution target | Approximately 0.4 MP, around 640×640 |
| Diffusion model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| Sampler | `res_multistep` |
| Scheduler | `simple` |
| Steps | 20 |
| Turbo LoRA installed | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` |
| Turbo LoRA enabled | No — `Boolean (Enable Lightning LoRA)` was false |

### Timing breakdown

| Phase | Approximate time |
|---|---:|
| Input conditioning and initial model reads | 163.7 seconds |
| Diffusion-model loading and initialization | 176.7 seconds |
| Twenty denoising steps | 219.2 seconds |
| VAE decoding, audio processing, and saving | 54.4 seconds |
| Small additional overhead | Approximately 4 seconds |
| **Total** | **617.969 seconds** |

During denoising:

- The GPU stayed close to 100% utilization.
- Power was approximately 333–335 W.
- Memory bandwidth utilization was approximately 86–88%.
- GPU memory usage was approximately 40.3 GB.
- Each denoising step took approximately 10.96 seconds.

This confirms that denoising was GPU-bound, while the long startup phases were dominated by model loading.

## Root-cause analysis

### 1. Cold model loading is the largest bottleneck

The ComfyUI process physically read **44,320,878,592 bytes**, approximately 44.3 GB, during the run. This closely matches the size of the optimized H3 model set.

At 125 MiB/s:

```text
44,320,878,592 bytes / 125 MiB/s ≈ 338 seconds ≈ 5 minutes 38 seconds
```

The two observed loading and initialization phases totaled approximately 340 seconds. This is strong evidence that gp3 throughput explains most of the cold-start delay.

The volume is created in `comfyui_aws_stack/construct/ecs_construct.py` with type and size only. Consequently, it receives the default gp3 throughput.

### 2. The workflow uses 20 steps unnecessarily

The installed Turbo LoRA is bypassed because its Boolean switch is false. Enabling the switch changes the graph to the LoRA branch and lower-step primitive.

At the measured 10.96 seconds per step:

| Step count | Estimated denoising time | Saving versus 20 steps |
|---:|---:|---:|
| 20 | 219 seconds | Baseline |
| 8 | 88 seconds | Approximately 132 seconds |
| 6 | 66 seconds | Approximately 153 seconds |
| 4 | 44 seconds | Approximately 175 seconds |

Reducing steps does not eliminate cold model-loading time. It becomes much more effective after storage caching or on a warm process.

### 3. The model format and CUDA runtime do not match

The current Docker image uses:

```dockerfile
FROM nvcr.io/nvidia/cuda:12.9.0-runtime-ubuntu22.04
```

PyTorch is installed from:

```text
https://download.pytorch.org/whl/cu126
```

The official ComfyUI MiniMax H3 model card recommends PyTorch cu130 for `int8_convrot` and recommends `fp8_scaled` when cu130 cannot be used.

Startup logs also reported:

- PyTorch cu130 or newer is needed for optimized CUDA operations.
- Comfy Kitchen CUDA and Triton backends were detected but disabled.
- ReActor's ONNX Runtime GPU provider could not find `libcublasLt.so.13`.

A CUDA 13/PyTorch cu130 rebuild should therefore be tested before changing GPU hardware.

### 4. Decode and save are secondary bottlenecks

Post-sampling work took approximately 54 seconds. This is meaningful but much smaller than model loading and denoising.

An upstream, unmerged ComfyUI pull request proposes keeping the MiniMax H3 audio VAE resident instead of dynamically offloading it. It may reduce audio decoding time, but it is experimental and should only be tested after the stable changes.

## Prioritized improvement checklist

### Phase 1: No infrastructure change

- [ ] Run the exact same workflow again without restarting the ECS task.
- [ ] Record the warm-run total and phase timings.
- [ ] Change `Boolean (Enable Lightning LoRA)` to true.
- [ ] Confirm that the LoRA branch and reduced-step branch are both selected.
- [ ] Use 8 steps for final output.
- [ ] Test 4 steps for previews.
- [ ] Add or verify `MiniMaxH3SigmaShift` with video shift `12` and audio shift `3`.
- [ ] Test the ModelTC reference workflow using Euler sampling and the simple scheduler.
- [ ] Keep output near 0.4 MP for the first comparison.
- [ ] Use 2–3 second preview clips while developing prompts.

Recommended Turbo presets:

| Preset | Steps | Intended use |
|---|---:|---|
| Quality | 8 | Final output |
| Balanced | 6 | Faster iteration with moderate quality tradeoff |
| Preview | 4 | Prompt and motion testing |

Expected result:

- Turbo alone should save approximately 2:12 at 8 steps.
- A warm run should also avoid a significant portion of the cold model-loading delay.

### Phase 2: CUDA 13 and PyTorch cu130

- [x] Change the Docker base image to CUDA 13.0.3.
- [x] Install and pin the matching PyTorch cu130 package set.
- [x] Pin the ComfyUI and ComfyUI Manager revisions.
- [x] Add build-time version/import assertions and runtime version logging.
- [ ] Rebuild and deploy the ComfyUI image.
- [ ] Confirm `torch.version.cuda` reports CUDA 13.
- [ ] Confirm the cu130 optimization warning disappears.
- [ ] Confirm Comfy Kitchen CUDA/Triton backends are available.
- [ ] Benchmark the default PyTorch attention backend.
- [ ] Benchmark `ModelAttentionBackend` with Comfy Kitchen attention.
- [ ] Keep only the faster configuration if output quality remains acceptable.

If cu130 cannot be deployed promptly:

- [ ] Benchmark the official `fp8_scaled` diffusion model instead of `int8_convrot`.

Do not assume that an attention backend is faster or equivalent without an A/B quality and timing test.

### Phase 3: Improve model storage

#### Preferred: local NVMe hot-model cache

The current `g6e.2xlarge` has an unused local NVMe device large enough for the approximately 44 GB H3 model set.

- [x] Format and mount the instance-store NVMe through host bootstrap.
- [x] Copy only manifest-selected H3 models from persistent EBS to NVMe.
- [x] Configure ComfyUI extra model paths to read NVMe first and EBS second.
- [x] Preserve the canonical copies on EBS because instance-store data is ephemeral.
- [x] Rebuild the cache automatically when a host is replaced.
- [x] Preserve the live REX-Ray volume name and pin the host to the volume's subnet.
- [ ] Deploy and verify cold cache population against the existing EBS volume.
- [ ] Optionally run a controlled warm-up workflow after startup.

Benefits:

- No additional monthly storage-throughput charge.
- Much faster repeated cold reads on the same EC2 host.

Tradeoffs:

- The cache disappears when the instance is terminated or replaced.
- Bootstrapping and cache validation need implementation.
- The first cache population still reads from EBS.

#### Simpler alternative: increase gp3 throughput

- [ ] Test 500 MiB/s.
- [ ] If model reads remain limited by EBS, test 625 MiB/s, the current instance's maximum EBS bandwidth.
- [ ] Keep the existing 3,000 IOPS initially; it is adequate for the proposed sequential-read throughput.
- [ ] Measure cold-run loading time before and after the change.

At the pricing observed during this investigation, additional gp3 throughput was approximately:

| Provisioned throughput | Approximate additional monthly cost |
|---:|---:|
| 500 MiB/s | $18/month above the included 125 MiB/s |
| 625 MiB/s | $24/month above the included 125 MiB/s |

Prices can change and must be verified before applying the modification.

### Phase 4: Optional ComfyUI experiments

- [ ] Evaluate the upstream MiniMax H3 audio-VAE offload patch in a separate image.
- [ ] Measure decode time before and after it.
- [ ] Evaluate upstream removal of per-step GPU-to-CPU synchronization after it is merged or reviewed.
- [ ] Test SageAttention only as an optional benchmark.
- [ ] Verify both speed and visual/audio quality.

Reasons for caution:

- Current SageAttention issues have been reported with H3 at large token counts and with Dynamic VRAM.
- The investigated workload is smaller and uses an Ada L40S, but that does not guarantee correctness.
- EasyCache can harm H3's audio stream and is not a recommended first optimization.

### Phase 5: Hardware changes

Only consider hardware after Turbo, cu130, and model storage are measured.

| Instance | Expected effect |
|---|---|
| `g6e.2xlarge` | Current L40S baseline; lowest-cost option in this comparison |
| `g6e.4xlarge` | Same L40S, so similar denoising speed; more RAM and EBS bandwidth improve loading/offloading headroom |
| `g7e.2xlarge` | One 96 GB Blackwell GPU; likely the best meaningful upgrade for this workflow |
| `g7e.4xlarge` | Same GPU as G7e.2 but more host RAM and higher EBS bandwidth |
| `p5.4xlarge` | One H100 with 80 GB; mature but substantially more expensive |

The live account check found `g7e.2xlarge` available in `ap-northeast-1c`. Its 96 GB GPU memory should allow more of the optimized H3 model set and working state to remain resident. AWS's published G7e performance claim is up to 2.3× G6e inference performance, but this is not a MiniMax H3-specific benchmark.

Moving from `g6e.2xlarge` to `g6e.4xlarge` should not be treated as a GPU sampling upgrade because both use one L40S.

## Expected performance targets

These are estimates to validate, not guarantees:

| Configuration | Estimated target |
|---|---:|
| Current cold 20-step workflow | Measured 10:18 |
| Image-only cu130 cold 8-step workflow on EBS | Measured 6:14.60 |
| Replacement-task cu130 cold 8-step workflow on EBS | Measured 6:17.66 |
| Cold 8-step Turbo without storage change | Approximately 8:06 |
| Cold 4-step Turbo without storage change | Approximately 7:23 |
| Warm or NVMe-cached 8-step Turbo on L40S | Approximately 2–4 minutes |
| cu130 plus fast storage plus 8-step Turbo | Benchmark target of approximately 2–4 minutes |
| G7e plus optimized workflow/storage | Potentially faster, but must be measured |

## Benchmark procedure

Change only one variable per test.

Use the same:

- Input image
- Prompt
- Negative prompt
- Seed
- Duration
- Resolution
- Frames per second
- Model files
- Output encoding

For each configuration:

1. Restart the ComfyUI task for a cold test.
2. Run the workflow once and record the cold time.
3. Run it again without restarting and record the warm time.
4. Record model-loading, initialization, sampling, and decode times separately.
5. Record seconds per denoising step.
6. Check GPU utilization, power, memory usage, and host RAM.
7. Compare video quality, motion, prompt adherence, and audio quality.

Suggested results table:

| Test | Runtime/model | Storage | Steps | Attention | Cold total | Warm total | Seconds/step | Quality notes |
|---|---|---|---:|---|---:|---:|---:|---|
| Baseline | cu126/int8 | gp3 125 MiB/s | 20 | PyTorch | 617.969 s | TBD | 10.96 s | Baseline |
| Turbo | cu126/int8 | gp3 125 MiB/s | 8 | PyTorch | TBD | TBD | TBD | |
| cu130 | cu130/int8 | gp3 125 MiB/s | 8 | PyTorch | 374.60 s | Not measured; ECS restarted | 3.81 s | Successful video; second cold run was 377.66 s after an OOM replacement |
| Faster EBS | cu130/int8 | gp3 500 MiB/s | 8 | PyTorch | TBD | TBD | TBD | |
| NVMe | cu130/int8 | Local NVMe | 8 | PyTorch | TBD | TBD | TBD | |
| Kitchen | cu130/int8 | Local NVMe | 8 | Comfy Kitchen | TBD | TBD | TBD | |

## Repository implementation points

| Change | File |
|---|---|
| CUDA base and PyTorch index | `comfyui_aws_stack/docker/Dockerfile` |
| Persistent gp3 volume definition | `comfyui_aws_stack/construct/ecs_construct.py` |
| Default GPU instance type | `comfyui_aws_stack/comfyui_aws_stack.py` |
| EC2 bootstrap and local NVMe mounting | `comfyui_aws_stack/construct/asg_construct.py` |

## Reference sources

- [ModelTC MiniMax H3 Turbo repository](https://github.com/ModelTC/Minimax-H3-Turbo)
- [Official Comfy-Org MiniMax H3 model card](https://huggingface.co/Comfy-Org/MiniMax-H3)
- [ComfyUI MiniMax H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
- [AWS gp3 documentation](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [AWS G6e instance specifications](https://aws.amazon.com/ec2/instance-types/g6e/)
- [AWS G7e announcement](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-ec2-g7e-instances-generally-available/)
- [ComfyUI PR #15371: MiniMax H3 audio VAE offload](https://github.com/Comfy-Org/ComfyUI/pull/15371)
- [ComfyUI PR #15560: MiniMax H3 per-step host synchronization](https://github.com/Comfy-Org/ComfyUI/pull/15560)
- [ComfyUI issue #15665: full-resolution H3 regression](https://github.com/Comfy-Org/ComfyUI/issues/15665)
- [PyTorch 2.14.0 release](https://github.com/pytorch/pytorch/releases/tag/v2.14.0)
- [Official PyTorch cu130 wheel index](https://download.pytorch.org/whl/cu130)
- [ComfyUI issue #15263: MiniMax H3 and SageAttention](https://github.com/Comfy-Org/ComfyUI/issues/15263)
- [ComfyUI issue #15566: SageAttention with Dynamic VRAM](https://github.com/Comfy-Org/ComfyUI/issues/15566)
