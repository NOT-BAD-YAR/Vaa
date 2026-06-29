from transformers import AutoProcessor
from transformers import AutoModelForImageTextToText

model_name = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"

print("Downloading processor...")

processor = AutoProcessor.from_pretrained(model_name)

print("Downloading model...")

model = AutoModelForImageTextToText.from_pretrained(
    model_name,
    device_map="auto"
)

print("Finished!")
