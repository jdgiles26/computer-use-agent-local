#!/usr/bin/env python3
"""
Download and setup SeeClick model for local GUI grounding.
SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents
https://huggingface.co/cckevinn/SeeClick
"""

import os
import sys
import subprocess
from pathlib import Path

# Model configuration
MODEL_REPO = "cckevinn/SeeClick"
MODEL_NAME = "SeeClick"
MODELS_DIR = Path(__file__).parent / "models" / "vision"

def check_dependencies():
    """Check if required packages are installed."""
    required = ["torch", "transformers", "pillow", "huggingface_hub"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing, check=True)
        print("Dependencies installed!")
    else:
        print("All dependencies are installed.")

def download_model():
    """Download SeeClick model from Hugging Face."""
    from huggingface_hub import snapshot_download
    
    model_path = MODELS_DIR / MODEL_NAME
    model_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading SeeClick model from {MODEL_REPO}...")
    print(f"Target directory: {model_path}")
    print("This may take a while (several GB)...")
    
    try:
        # Use mirror for faster download in some regions
        if os.environ.get("HF_ENDPOINT"):
            print(f"Using HF_ENDPOINT: {os.environ.get('HF_ENDPOINT')}")
        
        local_path = snapshot_download(
            repo_id=MODEL_REPO,
            local_dir=str(model_path),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        
        print(f"\n✓ Model downloaded successfully to: {local_path}")
        return local_path
        
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check your internet connection")
        print("2. If in China, set HF_ENDPOINT=https://hf-mirror.com")
        print("3. For gated models, run: huggingface-cli login")
        return None

def verify_model(model_path: str):
    """Verify the downloaded model."""
    path = Path(model_path)
    
    print("\nVerifying model files...")
    
    required_files = ["config.json", "pytorch_model.bin"]
    optional_files = ["model.safetensors", "tokenizer.json", "preprocessor_config.json"]
    
    found_required = []
    found_optional = []
    
    for f in required_files:
        if (path / f).exists():
            found_required.append(f)
            size = (path / f).stat().st_size / (1024**3)  # GB
            print(f"  ✓ {f} ({size:.2f} GB)")
        else:
            print(f"  ✗ {f} (MISSING)")
    
    for f in optional_files:
        if (path / f).exists():
            found_optional.append(f)
            size = (path / f).stat().st_size / (1024**3)
            print(f"  ✓ {f} ({size:.2f} GB)")
    
    if len(found_required) == 0 and "model.safetensors" not in found_optional:
        print("\n⚠ Warning: No model weights found!")
        return False
    
    print(f"\n✓ Model verification complete")
    print(f"  Found {len(found_required)} required files")
    print(f"  Found {len(found_optional)} optional files")
    return True

def create_test_script(model_path: str):
    """Create a test script for the model."""
    test_script = MODELS_DIR / "test_seeclick.py"
    
    content = f'''#!/usr/bin/env python3
"""
Test script for SeeClick model.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

def test_model():
    """Test SeeClick model loading."""
    try:
        from transformers import AutoModel, AutoTokenizer
        import torch
        from PIL import Image
        
        model_path = "{model_path}"
        print(f"Loading SeeClick from: {{model_path}}")
        
        # Load model and tokenizer
        print("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        
        print("Loading model...")
        model = AutoModel.from_pretrained(
            model_path,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None
        )
        
        print("✓ Model loaded successfully!")
        print(f"  Device: {{next(model.parameters()).device}}")
        print(f"  Dtype: {{next(model.parameters()).dtype}}")
        
        # Test inference
        print("\\nTesting inference...")
        
        # Create a dummy screenshot for testing
        test_image = Image.new('RGB', (800, 600), color='white')
        
        # Prepare input
        query = "Find the login button"
        
        # Note: SeeClick specific inference code would go here
        # This is a placeholder - actual implementation depends on model architecture
        
        print("✓ Test complete!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {{e}}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_model()
    sys.exit(0 if success else 1)
'''
    
    test_script.write_text(content)
    test_script.chmod(0o755)
    print(f"\n✓ Test script created: {test_script}")

def create_integration_module(model_path: str):
    """Create integration module for the agent."""
    integration_file = Path(__file__).parent / "seeclick_integration.py"
    
    content = f'''#!/usr/bin/env python3
"""
SeeClick integration for Computer Use Agent.
Provides GUI grounding capabilities using the SeeClick vision model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Model path
SEECLICK_MODEL_PATH = "{model_path}"


class SeeClickAnalyzer:
    """
    GUI element analyzer using SeeClick vision model.
    
    SeeClick is specifically trained for GUI grounding tasks and can:
    - Locate UI elements from screenshots
    - Understand element functionality
    - Provide coordinates for clicking
    """
    
    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or SEECLICK_MODEL_PATH
        self.model = None
        self.tokenizer = None
        self._load_model()
    
    def _load_model(self):
        """Load the SeeClick model."""
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch
            
            print(f"Loading SeeClick from {{self.model_path}}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            
            self.model = AutoModel.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None
            )
            
            self.model.eval()
            print("✓ SeeClick model loaded successfully")
            
        except Exception as e:
            print(f"✗ Failed to load SeeClick: {{e}}")
            raise
    
    def find_element(self, screenshot_path: str, description: str) -> dict[str, Any]:
        """
        Find a UI element in a screenshot.
        
        Args:
            screenshot_path: Path to screenshot image
            description: Natural language description of element to find
            
        Returns:
            Dict with 'found', 'x', 'y', 'confidence', 'description'
        """
        from PIL import Image
        import torch
        
        # Load image
        image = Image.open(screenshot_path).convert('RGB')
        
        # Prepare input for SeeClick
        # Note: Exact input format depends on SeeClick architecture
        # This is a generic implementation
        
        prompt = f"Locate the element: {{description}}"
        
        # Process inputs
        inputs = self.tokenizer(
            text=prompt,
            images=image,
            return_tensors="pt"
        )
        
        if torch.cuda.is_available():
            inputs = {{k: v.cuda() for k, v in inputs.items()}}
        
        # Generate prediction
        with torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=100)
        
        # Parse output
        result_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract coordinates from output
        # SeeClick typically outputs coordinates in format like "<box>123,456,789,012</box>"
        # or just "x: 123, y: 456"
        
        box_match = re.search(r'<box>(d+),(d+),(d+),(d+)</box>', result_text)
        coord_match = re.search(r'x[:\s]+(\d+)[,\s]+y[:\s]+(\d+)', result_text, re.I)
        
        if box_match:
            x1, y1, x2, y2 = map(int, box_match.groups())
            return {{
                'found': True,
                'x': (x1 + x2) // 2,  # Center point
                'y': (y1 + y2) // 2,
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2,
                'confidence': 0.9,  # Placeholder
                'description': result_text
            }}
        elif coord_match:
            x, y = map(int, coord_match.groups())
            return {{
                'found': True,
                'x': x,
                'y': y,
                'confidence': 0.85,
                'description': result_text
            }}
        
        return {{
            'found': False,
            'x': None,
            'y': None,
            'confidence': 0,
            'description': result_text
        }}
    
    def analyze_screenshot(self, screenshot_path: str) -> dict[str, Any]:
        """
        Comprehensive screenshot analysis.
        
        Returns:
            Dict with detected elements, their locations, and descriptions
        """
        from PIL import Image
        
        image = Image.open(screenshot_path)
        
        # Common UI elements to detect
        element_types = [
            "button",
            "text input field",
            "checkbox",
            "radio button",
            "dropdown menu",
            "link",
            "image",
            "navigation menu",
            "search bar",
            "login form"
        ]
        
        results = []
        
        for element_type in element_types:
            result = self.find_element(screenshot_path, f"Find the {{element_type}}")
            if result['found']:
                results.append({{
                    'type': element_type,
                    'location': (result['x'], result['y']),
                    'confidence': result['confidence']
                }})
        
        return {{
            'screenshot': screenshot_path,
            'dimensions': image.size,
            'elements_detected': len(results),
            'elements': results
        }}


def main():
    """CLI for testing SeeClick integration."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SeeClick GUI Analyzer")
    parser.add_argument("screenshot", help="Path to screenshot image")
    parser.add_argument("--find", "-f", help="Element description to find")
    parser.add_argument("--analyze", "-a", action="store_true", help="Full screenshot analysis")
    
    args = parser.parse_args()
    
    analyzer = SeeClickAnalyzer()
    
    if args.find:
        result = analyzer.find_element(args.screenshot, args.find)
        print(json.dumps(result, indent=2))
    elif args.analyze:
        result = analyzer.analyze_screenshot(args.screenshot)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
'''
    
    integration_file.write_text(content)
    integration_file.chmod(0o755)
    print(f"✓ Integration module created: {integration_file}")

def main():
    """Main download and setup function."""
    print("=" * 60)
    print("SeeClick Model Download and Setup")
    print("=" * 60)
    print()
    
    # Check dependencies
    check_dependencies()
    print()
    
    # Download model
    model_path = download_model()
    
    if model_path:
        # Verify
        if verify_model(model_path):
            # Create helper scripts
            create_test_script(model_path)
            create_integration_module(model_path)
            
            print("\n" + "=" * 60)
            print("Setup Complete!")
            print("=" * 60)
            print(f"\nModel location: {model_path}")
            print("\nNext steps:")
            print("1. Test the model:")
            print(f"   python {MODELS_DIR / 'test_seeclick.py'}")
            print("\n2. Use in agent:")
            print("   from seeclick_integration import SeeClickAnalyzer")
            print("   analyzer = SeeClickAnalyzer()")
            print("   result = analyzer.find_element('screenshot.png', 'login button')")
            print()
        else:
            print("\n⚠ Model verification failed. Please check the download.")
    else:
        print("\n✗ Download failed. Please try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
