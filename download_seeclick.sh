#!/bin/bash
#
# Download SeeClick model using huggingface-cli
# SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents
# Repository: https://huggingface.co/cckevinn/SeeClick
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
MODEL_REPO="cckevinn/SeeClick"
MODEL_DIR="models/vision/SeeClick"

print_header() {
    echo ""
    echo "============================================================"
    echo "SeeClick Model Downloader"
    echo "============================================================"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

check_dependencies() {
    echo "Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! python3 -c "import huggingface_hub" 2>/dev/null; then
        print_warning "huggingface_hub not found. Installing..."
        pip3 install huggingface_hub
    fi
    
    print_success "Dependencies OK"
}

download_model() {
    echo ""
    echo "Downloading SeeClick model..."
    echo "Repository: $MODEL_REPO"
    echo "Target: $MODEL_DIR"
    echo ""
    
    # Create directory
    mkdir -p "$MODEL_DIR"
    
    # Download using huggingface-cli
    if huggingface-cli download \
        --resume-download \
        --local-dir-use-symlinks False \
        --local-dir "$MODEL_DIR" \
        "$MODEL_REPO"; then
        print_success "Download complete!"
    else
        print_error "Download failed"
        
        echo ""
        echo "Troubleshooting:"
        echo "1. Check internet connection"
        echo "2. If in China, set mirror:"
        echo "   export HF_ENDPOINT=https://hf-mirror.com"
        echo "3. For authentication issues:"
        echo "   huggingface-cli login"
        exit 1
    fi
}

verify_model() {
    echo ""
    echo "Verifying model files..."
    
    REQUIRED_FILES=("config.json")
    WEIGHT_FILES=("pytorch_model.bin" "model.safetensors")
    
    found_weights=false
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$MODEL_DIR/$file" ]; then
            print_success "Found $file"
        else
            print_error "Missing $file"
        fi
    done
    
    for file in "${WEIGHT_FILES[@]}"; do
        if [ -f "$MODEL_DIR/$file" ]; then
            size=$(du -h "$MODEL_DIR/$file" | cut -f1)
            print_success "Found $file ($size)"
            found_weights=true
        fi
    done
    
    if [ "$found_weights" = false ]; then
        print_error "No model weights found!"
        return 1
    fi
    
    return 0
}

show_usage() {
    echo ""
    echo "============================================================"
    echo "Setup Complete!"
    echo "============================================================"
    echo ""
    echo "Model location: $(pwd)/$MODEL_DIR"
    echo ""
    echo "Usage in Python:"
    echo ""
    echo "  from transformers import AutoModel, AutoTokenizer"
    echo ""
    echo "  # Load model"
    echo "  model_path = '$MODEL_DIR'"
    echo "  tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)"
    echo "  model = AutoModel.from_pretrained(model_path, trust_remote_code=True)"
    echo ""
    echo "  # Use for GUI grounding"
    echo "  # (See seeclick_integration.py for full example)"
    echo ""
    echo "Test the model:"
    echo "  python3 models/vision/SeeClick/test_seeclick.py"
    echo ""
}

# Main
print_header
check_dependencies
download_model

if verify_model; then
    # Create __init__.py for Python module
    touch "$MODEL_DIR/__init__.py"
    show_usage
else
    print_error "Model verification failed"
    exit 1
fi
