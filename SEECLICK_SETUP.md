# SeeClick Model Setup

SeeClick is a vision-language model specifically trained for **GUI grounding** - locating UI elements from screenshots.

## Quick Start

### Option 1: Using the GUI
1. Start the agent GUI: `./launch-agent-gui.sh`
2. Click the **"Models"** menu
3. Select **"Download SeeClick (Vision Model)"**
4. Wait for download to complete (several GB)

### Option 2: Using Command Line

```bash
# Using the shell script
./download_seeclick.sh

# Or using Python
python3 download_seeclick.py
```

### Option 3: Manual Download

```bash
# Install huggingface-cli
pip install huggingface-hub

# Download model
huggingface-cli download \
    --resume-download \
    --local-dir-use-symlinks False \
    --local-dir models/vision/SeeClick \
    cckevinn/SeeClick
```

## Model Information

- **Repository**: [cckevinn/SeeClick](https://huggingface.co/cckevinn/SeeClick)
- **Base Model**: Qwen-VL (7B parameters)
- **Training**: Fine-tuned on GUI grounding datasets
- **Size**: ~14 GB (FP16) or ~7 GB (INT8 quantized)
- **License**: Check Hugging Face repository for license details

## Requirements

- **Python**: 3.8+
- **RAM**: 16 GB minimum (32 GB recommended)
- **GPU**: Optional but recommended (CUDA-compatible)
- **Storage**: 15 GB free space

## Python Dependencies

```bash
pip install torch transformers pillow huggingface_hub
```

For GPU support:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## Usage Example

```python
from seeclick_integration import SeeClickAnalyzer

# Initialize analyzer
analyzer = SeeClickAnalyzer()

# Find an element in a screenshot
result = analyzer.find_element(
    screenshot_path="output/desktop/screenshot.png",
    description="login button"
)

if result['found']:
    print(f"Element found at: ({result['x']}, {result['y']})")
    print(f"Confidence: {result['confidence']}")
else:
    print("Element not found")

# Full screenshot analysis
analysis = analyzer.analyze_screenshot("screenshot.png")
print(f"Detected {analysis['elements_detected']} elements")
```

## Integration with Agent

The agent can use SeeClick as a fallback when DOM-based element detection fails:

```python
# In your agent code
from seeclick_integration import SeeClickAnalyzer

class EnhancedAgent:
    def __init__(self):
        self.vision_analyzer = None
        try:
            self.vision_analyzer = SeeClickAnalyzer()
        except Exception as e:
            print(f"Vision model not available: {e}")
    
    def find_element(self, description: str):
        # Try DOM first (fast)
        element = self.browser.find_by_accessibility_tree(description)
        
        if not element and self.vision_analyzer:
            # Fallback to vision (slower but more accurate)
            screenshot = self.browser.screenshot()
            result = self.vision_analyzer.find_element(screenshot, description)
            if result['found']:
                return result
        
        return element
```

## Troubleshooting

### Download Issues

**Slow download in China:**
```bash
export HF_ENDPOINT=https://hf-mirror.com
./download_seeclick.sh
```

**Resume interrupted download:**
The download script automatically resumes. Just run it again.

**Out of disk space:**
SeeClick requires ~15 GB. Check space with:
```bash
df -h .
```

### Memory Issues

**Loading fails with OOM:**
Use quantization to reduce memory:
```python
model = AutoModel.from_pretrained(
    model_path,
    trust_remote_code=True,
    load_in_8bit=True,  # or load_in_4bit=True
    device_map="auto"
)
```

### GPU Issues

**CUDA out of memory:**
The model will automatically fall back to CPU. To force CPU:
```python
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
```

## Performance

| Hardware | Load Time | Inference Time | Memory |
|----------|-----------|----------------|--------|
| CPU (16 cores) | ~30s | ~5-10s | ~14 GB |
| GPU (RTX 3090) | ~10s | ~0.5-1s | ~8 GB |
| GPU (A100) | ~5s | ~0.2s | ~8 GB |
| Mac M2 | ~20s | ~3-5s | ~14 GB |

## Benchmarks

SeeClick achieves state-of-the-art performance on GUI grounding:

| Benchmark | Accuracy |
|-----------|----------|
| ScreenSpot | ~85% |
| Mind2Web | ~78% |
| AITW | ~72% |

Compared to general vision models:
- **CLIP**: ~45% on GUI tasks
- **Qwen-VL**: ~70% on GUI tasks
- **SeeClick**: ~85% on GUI tasks (specialized)

## Citation

If you use SeeClick in research, please cite:

```bibtex
@inproceedings{cheng2024seeclick,
  title={SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents},
  author={Cheng, Kanzhi and Sun, Qiushi and Chu, Yougang and Xu, Fangzhi and YanTao, Li and Zhang, Jianbing and Wu, Zhiyong},
  booktitle={Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics},
  year={2024}
}
```

## See Also

- [VISION_MODELS.md](VISION_MODELS.md) - Comparison of vision models
- [SeeClick Paper](https://arxiv.org/abs/2401.10935)
- [SeeClick GitHub](https://github.com/njucckevin/SeeClick)
