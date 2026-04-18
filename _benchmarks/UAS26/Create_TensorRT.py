# ****Run these in terminal****
# pip install ultralyticsplus==0.0.28 ultralytics==8.0.43
# pip install onnxscript onnx

import torch
from ultralytics import YOLO
from ultralyticsplus import YOLO as YOLOplus

print("***Starting Standard Export***")
model_std = YOLO('yolov8n.pt')
model_std_file = model_std.export(format='engine', half=True, workspace=1)
print(f'yolov8n standard saved as tensorrt file @: {model_std_file}')

print("***Starting VisDrone Export***")
_original_load = torch.load
torch.load = lambda *args, **kwargs: _original_load(*args, **{**kwargs, 'weights_only': False})
model_VisDrone = YOLOplus('mshamrai/yolov8n-visdrone')
model_VisDrone_file = model_VisDrone.export(format='engine', half=True, workspace=1)
print(f'yolov8n VisDrone saved as tensorrt file @: {model_VisDrone_file}')
torch.load = _original_load

print("Done, Exported both files successfully")