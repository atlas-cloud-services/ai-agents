from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI(title="ACS GMAO AI - LLM Service")

# Configure for Mac M1
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Using device: {device}")

# Load a small model suitable for Mac M1
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Small model that works on Mac M1

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True
    ).to(device)
    print("Model loaded successfully")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None
    tokenizer = None

class GenerateRequest(BaseModel):
    prompt: str
    max_length: Optional[int] = 512
    temperature: Optional[float] = 0.7

class GenerateResponse(BaseModel):
    text: str
    processing_time: float

@app.get("/")
def read_root():
    return {"status": "LLM Service is running"}

@app.post("/generate", response_model=GenerateResponse)
async def generate_text(request: GenerateRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    import time
    start_time = time.time()
    
    # Create input tokens
    inputs = tokenizer(request.prompt, return_tensors="pt").to(device)
    
    # Generate text
    with torch.no_grad():
        outputs = model.generate(
            inputs["input_ids"],
            max_length=request.max_length,
            temperature=request.temperature,
            do_sample=True,
        )
    
    # Decode the generated text
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Remove the prompt from the generated text
    response_text = generated_text[len(request.prompt):] if generated_text.startswith(request.prompt) else generated_text
    
    processing_time = time.time() - start_time
    
    return {"text": response_text, "processing_time": processing_time}