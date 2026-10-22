"""Offline image inference only. No simulator state, object truth or flight tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
from adapters.vision_reviewer import ROOT, SMOL_PROMPT, FLORENCE_PROMPT


def main(name):
    os.environ.setdefault('HF_HOME',str(ROOT/'.local/huggingface'))
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
    import torch
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    torch.set_num_threads(2);torch.manual_seed(0)
    folder=ROOT/'.local/data/vision-reviewers'/name
    manifest=json.loads((folder/'manifest.json').read_text())
    for file,record in manifest['files'].items():
        with (folder/file).open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=record['sha256']:raise ValueError('Checkpoint hash mismatch: '+file)
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    dtype=torch.float16 if device=='mps' else torch.float32
    # Absolute allocation budget: using a fixed fraction would halve the model's
    # allowance on an 8 GiB host and prevent otherwise fitting weights loading.
    if device=='mps':torch.mps.set_per_process_memory_fraction(min(1.,1.9*1024**3/torch.mps.recommended_max_memory()))
    began=time.monotonic()
    if name=='florence':
        from transformers import AutoModelForCausalLM
        processor=AutoProcessor.from_pretrained(folder,trust_remote_code=True,local_files_only=True)
        model=AutoModelForCausalLM.from_pretrained(folder,trust_remote_code=True,local_files_only=True,
                                                  torch_dtype=dtype,attn_implementation='eager').to(device).eval()
    else:
        processor=AutoProcessor.from_pretrained(folder,local_files_only=True)
        # Candidate crops are already small. The checkpoint's default 2048px
        # tiling magnifies them into many redundant tiles and exceeds our RAM
        # allocation. One native 512px tile retains all source pixels.
        processor.image_processor.size={'longest_edge':512}
        processor.image_processor.do_image_splitting=False
        model=AutoModelForImageTextToText.from_pretrained(folder,local_files_only=True,
            torch_dtype=dtype,attn_implementation='sdpa').to(device).eval()
    print(json.dumps({'ready':True,'model':name,'manifest':manifest,'device':device,'dtype':str(dtype),
                      'load_seconds':time.monotonic()-began,
                      'attention':'eager' if name=='florence' else 'sdpa',
                      'gpu_allocation_budget_gib':1.9,
                      'preprocessing':{'image_size':processor.image_processor.size,
                                       'image_splitting':getattr(processor.image_processor,'do_image_splitting',False)}}),flush=True)
    for line in sys.stdin:
        try:
            data=json.loads(line);path=Path(data['image']).resolve()
            if not path.is_relative_to(ROOT/'.local/validation'):raise ValueError('Image outside evaluation directory')
            image=Image.open(path).convert('RGB');began=time.monotonic()
            if name=='florence':
                inputs=processor(text=FLORENCE_PROMPT,images=image,return_tensors='pt').to(device,dtype)
            else:
                messages=[{'role':'user','content':[{'type':'image'},{'type':'text','text':SMOL_PROMPT}]}]
                prompt=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=False)
                inputs=processor(text=prompt,images=[image],return_tensors='pt').to(device,dtype)
            with torch.inference_mode():
                output=model.generate(**inputs,max_new_tokens=96,do_sample=False,num_beams=1,use_cache=name!='florence')
            if name=='florence':
                raw=processor.batch_decode(output,skip_special_tokens=False)[0]
                caption=processor.post_process_generation(raw,task=FLORENCE_PROMPT,image_size=image.size)[FLORENCE_PROMPT]
            else:
                raw=processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0];caption=raw
            print(json.dumps({'caption':caption,'raw':raw,'inference_seconds':time.monotonic()-began,
                              'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}),flush=True)
            del inputs,output
            if device=='mps':torch.mps.empty_cache()
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'error':repr(e)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['florence','smolvlm'],required=True)
    try:main(p.parse_args().model)
    except Exception as e:print(json.dumps({'error':repr(e)}),flush=True);raise
