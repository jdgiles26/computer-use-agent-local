# Vision Model Integration for Computer Use Agents

## Current Architecture

The agent currently uses **text-based interaction** with the browser through:
- Accessibility tree snapshots (Playwright's built-in element detection)
- DOM parsing and element extraction
- JavaScript evaluation for dynamic content

Screenshots are captured but **not analyzed by vision models** - they're only for human review.

## Would Vision Models Improve Accuracy?

### Short Answer: **Yes, but with caveats**

Vision-Language Models (VLMs) can significantly improve accuracy for:
1. **Visual element detection** - Finding buttons, forms, icons that accessibility trees miss
2. **Spatial reasoning** - Understanding layout and relative positions
3. **Dynamic content** - Handling canvas-based apps, complex visual UIs
4. **Cross-platform consistency** - Works across web, desktop, mobile

### Research Findings

According to recent studies (2024):

| Model Type | GUI Grounding Accuracy | Notes |
|------------|------------------------|-------|
| Text-only (DOM) | ~60-70% | Fast, misses visual elements |
| CLIP-based | ~75-85% | Good zero-shot, struggles with fine-grained UI |
| Fine-tuned VLMs (Qwen-VL, SeeClick) | ~85-95% | Best for GUI tasks, requires training |
| GPT-4V/Claude 3.5 Sonnet | ~90-95% | State-of-the-art, expensive |
| UI-TARS (specialized) | ~92%+ | Specifically trained for UI automation |

### Vision Model Options

#### 1. **OpenCLIP** (Open Source)
```python
# Pros:
- Free and open source
- Good zero-shot performance
- Can be run locally

# Cons:
- Not specifically trained for UI/GUI tasks
- Struggles with small UI elements
- Requires prompt engineering
- ~75-80% accuracy on GUI tasks

# Best for:
- General image understanding
- Icon recognition
- High-level visual analysis
```

#### 2. **BERT-based Vision Models** (e.g., LISA, PixelBERT)
```python
# Pros:
- Good text + image understanding
- Can be fine-tuned

# Cons:
- BERT is primarily text-based
- Vision variants are older (2020-2021)
- Not competitive with modern VLMs
- Not recommended for new projects
```

#### 3. **Qwen-VL / Qwen2-VL** (Alibaba, Open Source)
```python
# Pros:
- Specifically trained for UI tasks
- High accuracy (85-90%)
- Can run locally (7B-72B params)
- Good at element grounding

# Cons:
- Requires GPU for good performance
- Chinese model (may have English quirks)

# Best for:
- Production GUI automation
- Multi-language UI support
```

#### 4. **SeeClick** (Specialized GUI Model)
```python
# Pros:
- Specifically designed for GUI grounding
- Trained on UI screenshots
- High accuracy on element detection
- ~90%+ on Mind2Web benchmark

# Cons:
- Requires fine-tuning for best results
- Limited to click/typing actions

# Best for:
- Precise element localization
- Web automation
```

#### 5. **UI-TARS** (ByteDance, State-of-the-art)
```python
# Pros:
- SOTA performance (92%+ on WebVoyager)
- Specifically trained for UI automation
- Handles complex multi-step tasks
- Vision + action prediction

# Cons:
- Requires API access or large local setup
- 7B-72B parameter models

# Best for:
- Production computer use agents
- Complex task automation
```

#### 6. **GPT-4V / Claude 3.5 Sonnet** (Commercial)
```python
# Pros:
- Best general performance
- Excellent reasoning
- No training required

# Cons:
- Expensive per API call
- Requires internet connection
- Privacy concerns

# Best for:
- Prototyping
- Complex reasoning tasks
- When accuracy is critical
```

## Implementation Options

### Option 1: Screenshot Analysis Pipeline
```python
# Add to agent workflow:
1. Take screenshot
2. Send to VLM with prompt: "What UI elements are visible?"
3. Parse VLM response for element locations
4. Convert to coordinates/actions
5. Execute action

# Pros: Simple to implement
# Cons: Adds latency, API costs
```

### Option 2: Hybrid Approach (Recommended)
```python
# Use both DOM and Vision:
1. Get accessibility tree (fast)
2. If confidence low or element not found:
   a. Take screenshot
   b. Query VLM for element location
   c. Use VLM coordinates
3. Fall back to vision for canvas/SVG elements

# Pros: Best accuracy, efficient
# Cons: More complex implementation
```

### Option 3: Vision-First (Future)
```python
# Replace DOM entirely with vision:
1. Screenshot → VLM → Action
2. No HTML parsing needed
3. Works across platforms (web/desktop/mobile)

# Pros: Universal, handles any UI
# Cons: Higher latency, cost
```

## Recommendation for This Project

### Phase 1: Current (Text-based)
- Keep current Playwright + accessibility tree approach
- Fast and cost-effective
- Good for 70-80% of tasks

### Phase 2: Hybrid (Add Vision)
- Integrate Qwen2-VL or SeeClick (local models)
- Use vision when:
  - Element not found in DOM
  - Canvas/SVG content
  - Visual verification needed
  - Confidence score is low

### Phase 3: Advanced (Optional)
- Add UI-TARS or GPT-4V for complex tasks
- Full vision-based mode for difficult sites

## Quick Implementation: Add OpenCLIP

If you want to experiment with vision models quickly:

```python
# Add to computer_use_agent.py

class VisionAnalyzer:
    def __init__(self):
        try:
            import open_clip
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32', pretrained='openai'
            )
            self.tokenizer = open_clip.get_tokenizer('ViT-B-32')
            self.available = True
        except ImportError:
            self.available = False
    
    def find_element(self, screenshot_path: str, description: str) -> tuple[int, int] | None:
        """Find element in screenshot matching description."""
        if not self.available:
            return None
        
        import torch
        from PIL import Image
        
        image = Image.open(screenshot_path)
        image_tensor = self.preprocess(image).unsqueeze(0)
        text_tensor = self.tokenizer([description])
        
        with torch.no_grad():
            image_features = self.model.encode_image(image_tensor)
            text_features = self.model.encode_text(text_tensor)
            similarity = (image_features @ text_features.T).squeeze()
        
        # This gives image-text similarity, not coordinates
        # For coordinates, need detection model like GroundingDINO
        return None
```

**Note:** CLIP alone doesn't give coordinates. You need:
- **GroundingDINO** or **SAM** (Segment Anything) for object detection
- Or a specialized UI model like SeeClick

## Best Local Vision Model for GUI

For immediate integration, **Qwen2-VL** is recommended:

```bash
# Install
pip install transformers torch Pillow

# Download model (7B fits in 16GB VRAM)
# Can run on CPU with quantization
```

```python
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

class QwenVisionAnalyzer:
    def __init__(self):
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2-VL-7B-Instruct",
            torch_dtype="auto",
            device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(
            "Qwen/Qwen2-VL-7B-Instruct"
        )
    
    def analyze_screenshot(self, image_path: str, query: str) -> str:
        from PIL import Image
        image = Image.open(image_path)
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": query}
            ]
        }]
        
        text = self.processor.apply_chat_template(messages, tokenize=False)
        inputs = self.processor(text=[text], images=[image], return_tensors="pt")
        inputs = inputs.to(self.model.device)
        
        outputs = self.model.generate(**inputs, max_new_tokens=100)
        return self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
```

## Conclusion

**For your use case:**
1. **Screenshots are saved to** `output/desktop/` - not your Desktop
2. **Vision models would help** for complex visual UIs, but:
   - Add latency (500ms-2s per query)
   - Require GPU or API costs
   - Current text-based approach works for most web tasks
3. **Best upgrade path:** Hybrid approach with Qwen2-VL for difficult cases

**Immediate recommendation:**
- Keep current architecture
- Add vision as optional enhancement for specific tasks
- Use UI-TARS or GPT-4V API only when needed
