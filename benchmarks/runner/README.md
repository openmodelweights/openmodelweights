# OMW reproducible GPU benchmark runner

This runner produces **real deployment measurements** for the Open Model Weights benchmark corpus. It is intentionally NVIDIA/vLLM-first for the launch version so that the first measurements use one tightly controlled runtime rather than mixing incomparable stacks.

## Host requirements

- Linux
- NVIDIA GPU with working `nvidia-smi`
- Python 3.10+
- enough local disk for the model weights
- Hugging Face access if the selected repository is gated
- a clean/dedicated GPU host is strongly preferred

Install a vLLM build appropriate for the host CUDA/PyTorch stack, then:

```bash
pip install -r benchmarks/runner/requirements.txt
```

## Run

From a checkout of this repository:

```bash
python benchmarks/runner/omw_vllm_benchmark.py \
  --model-id qwen-qwen2-5-1-5b-instruct \
  --write-repo
```

The runner resolves the current Open Model Weights source repository, pins the exact Hugging Face repository SHA, launches a local vLLM OpenAI-compatible server, performs 2 warmups and 5 measured deterministic streaming generations, samples GPU memory with `nvidia-smi`, and records:

- exact source repository SHA
- vLLM/PyTorch/Python versions
- GPU model, VRAM, driver and reported CUDA version
- exact server command
- fixed prompt and token counts
- TTFT for every run
- output token throughput for every run
- GPU-memory samples and peak
- median headline metrics
- raw server log

With `--write-repo`, the accepted-shape result is appended to `data/benchmark-results.json` and the raw evidence is written to `data/benchmark-evidence/<result_id>.json`.

## Important

Do not compare results across different precisions, quantizations, runtimes, tensor-parallel layouts or hardware as though they were one benchmark class. OMW publishes observations and their environment; it does not turn them into a universal model-quality score.

For a first public run, start with a small model that comfortably fits on the available GPU. Once the path is validated, repeat the same protocol on larger representative models.
