#!/usr/bin/env python3
"""Read-only source/payload closure gate for the crDroid 13 M11 IMS port."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, struct, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEV=Path("device/samsung/m11q")
BASE="0f1da5855d27841d53743cd878ecd2d09679a941"
APK={"imsservice":"ims/proprietary/priv-app/imsservice/imsservice.apk",
"sveservice":"ims/proprietary/app/sveservice/sveservice.apk",
"EpdgService":"ims/proprietary/priv-app/EpdgService/EpdgService.apk",
"UnifiedWFC":"ims/proprietary/app/UnifiedWFC/UnifiedWFC.apk"}
OUT={"imsservice":"ims-lg3-unsigned.apk","sveservice":"sveservice-sv1-source-verified-unsigned.apk",
"EpdgService":"EpdgService-lg2-source-verified-unsigned.apk","UnifiedWFC":"UnifiedWFC-uw1-unsigned.apk"}
ERIS={n:f"ims/proprietary/lib/arm/{n}" for n in ("liberc.so","libers.so","liberis_strongswan.so")}

def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
def reg(p):
 if p.is_symlink() or not p.is_file(): raise ValueError(f"missing/unsafe file: {p}")
 return p.resolve(strict=True)
def module(root,name):
 path=root/"tools"/(name+".py"); spec=importlib.util.spec_from_file_location("_verify_"+name,path)
 if not spec or not spec.loader: raise ValueError(f"cannot load public tool {path}")
 obj=importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj
def copies(root,compat):
 rows=module(compat,"verify_payload").load_manifest(compat/"devices/m11q/payload-manifest.tsv")
 rows=[x for x in rows if x["action"]=="copy"]
 if len(rows)!=40: raise ValueError(f"manifest copy rows={len(rows)}, expected 40")
 bad=[]; checked=0
 for r in rows:
  rel=r["destination_rel"]; p=root/DEV/rel
  try:
   if rel.parts[0]!="ims": raise ValueError("destination outside ims/")
   reg(p)
   if p.stat().st_size!=r["stock_size"] or sha(p)!=r["stock_sha256"]: raise ValueError("stock SHA/size mismatch")
   checked+=1
  except (OSError,ValueError) as e: bad.append({"destination":str(rel),"error":str(e)})
 return {"expected":40,"checked":checked,"failed":bad}
def audio(stock,out,report):
 data=reg(stock).read_bytes()
 if sha(stock)!="c9242fe987c93b2363875e1dfbb9a2450676e3d68cd56b78b15a53a6604e52c4": raise ValueError("stock AudioFW SHA mismatch")
 if data[:6]!=b"\x7fELF\x01\x01" or struct.unpack_from("<H",data,18)[0]!=40: raise ValueError("AudioFW input is not ARM ELF32")
 old,new=b"framework-permission-aidl-cpp.so\0",b"libm11q_sve_compat.so\0"
 if data.count(old)!=1: raise ValueError("AudioFW dependency occurrence mismatch")
 expected=bytearray(data.replace(old,new.ljust(len(old),b"\0"),1))
 for i in (26,41,34,28,44,37):
  o=0x1AC+i*0x10; expected[o+4:o+12]=b"\0"*8; expected[o+14:o+16]=b"\0"*2
 actual=reg(out).read_bytes()
 if actual!=bytes(expected): raise ValueError("AudioFW staged file differs from public transform")
 r=json.loads(reg(report).read_text(encoding="utf-8"))
 if r.get("status")!="PASS" or r.get("output_sha256")!=sha(out): raise ValueError("AudioFW report hash/status mismatch")
 return {"status":"PASS","input_sha256":sha(stock),"output_sha256":sha(out)}
def prebuilt_jni_entries(block):
 lines=block.splitlines(); entries=[]; i=0; slash=chr(92)
 while i<len(lines):
  line=lines[i]
  if not line.lstrip().startswith("LOCAL_PREBUILT_JNI_LIBS :="):
   i+=1; continue
  value=line.split(":=",1)[1].strip(); more=value.endswith(slash)
  value=value.rstrip(slash).strip()
  if value: entries.append(value)
  while more and i+1<len(lines):
   i+=1; value=lines[i].strip(); more=value.endswith(slash)
   value=value.rstrip(slash).strip()
   if value: entries.append(value)
  return entries
 return entries

def check_native_wiring(bp,mk):
 mods=("libm11q_sve_compat","lib_android_FrameCapture")
 if bp.count('compile_multilib: "32"')!=2 or not all(f'name: "{n}"' in bp for n in mods): raise ValueError("SVE Soong declarations must be ARM32")
 blocks=re.findall(r"cc_library_shared\s*\{([^{}]*)\}",bp)
 compat=[b for b in blocks if re.search(r'name:\s*"libm11q_sve_compat"',b)]
 if len(compat)!=1 or not re.search(r'header_libs:\s*\[[^]]*"libmedia_headers"',compat[0],re.S): raise ValueError("libm11q_sve_compat must declare libmedia_headers")
 app=re.search(r"LOCAL_MODULE := sveservice([\s\S]*?)include \$\(BUILD_PREBUILT\)",mk)
 if not app or "LOCAL_JNI_SHARED_LIBRARIES := libm11q_sve_compat lib_android_FrameCapture" not in app.group(1): raise ValueError("sveservice JNI shared deps missing")
 entries=prebuilt_jni_entries(app.group(1))
 if any(any(n in entry for n in mods) for entry in entries): raise ValueError("SVE helpers still prebuilt")
 return {"status":"PASS","arm32_modules":list(mods),"media_headers":True}

def check_uw1_identity(report_value, contract):
 identity=contract.get("transformation_id")
 if not isinstance(identity,str) or not identity or report_value.get("transformation_id")!=identity:
  raise ValueError("UW1 report transformation identity differs from public contract")
 return identity

def native(root):
 d=root/DEV; base=d/"ims/compat/sve"; git=["git","-C",str(d)]
 head=subprocess.run(git+["rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
 if head!=BASE: raise ValueError(f"device base HEAD mismatch: {head}")
 names=("m11q_sve_compat.cpp","m11q_framecapture_stub.c")
 for n in names:
  if reg(base/n).read_bytes()!=subprocess.run(git+["show",f"{BASE}:ims/compat/sve/{n}"],capture_output=True,check=True).stdout: raise ValueError(f"SVE source differs from public base: {n}")
 bp=reg(base/"Android.bp").read_text(); mk=reg(d/"ims/Android.mk").read_text()
 wiring=check_native_wiring(bp,mk)
 return {"status":"PASS","device_base":head,"unchanged_sources":list(names),"arm32_modules":wiring["arm32_modules"],"media_headers":wiring["media_headers"],"native_compile":"PENDING_USER_ANDROID_BUILD"}
def source(root):
 d=root/DEV; prop=reg(d/"system.prop").read_text()
 for k,v in (("ro.telephony.iwlan_operation_mode","legacy"),("ro.m11q.ims_trial","legacy-r1"),("ro.m11q.ims_seh_apn_bridge","true")):
  if not re.search(rf"(?m)^{re.escape(k)}={re.escape(v)}$",prop): raise ValueError(f"missing source property {k}={v}")
 if "inherit-product, device/samsung/m11q/ims/ims.mk" not in reg(d/"device.mk").read_text(): raise ValueError("device.mk missing IMS product inheritance")
 ims=reg(d/"ims/ims.mk").read_text()
 if "PRODUCT_PACKAGES +=" not in ims or not all(x in ims for x in ("imsservice","sveservice","EpdgService","UnifiedWFC")): raise ValueError("IMS PRODUCT_PACKAGES incomplete")
 for folder in (d,d/"ims/sepolicy",d/"sepolicy",d/"rootdir"):
  if folder.exists():
   for p in folder.rglob("*"):
    if p.is_file() and not p.is_symlink() and p.suffix in {".mk",".prop",".rc",".te"}:
     t=p.read_text(encoding="utf-8",errors="ignore")
     if re.search(r"(?im)(androidboot\.selinux\s*=\s*permissive|setenforce\s+0|^\s*permissive\s+\w+)",t): raise ValueError(f"SELinux permissive override: {p.relative_to(d)}")
 return {"status":"PASS","legacy_iwlan":True,"seh_apn_bridge":True,"ims_product_inheritance":True,"selinux":"no device-local permissive override found"}
def makepaths(root):
 d=root/DEV; txt=reg(d/"ims/Android.mk").read_text(); refs=set(re.findall(r"(proprietary/[^\s\\]+)",txt)); paths=set()
 for raw in refs:
  raw=raw.rstrip("\\")
  if "$(2)" in raw:
   for n in ("liberis_strongswan","liberis_charon","liberis_simaka","libsecril-client"): paths.add(raw.replace("$(2)",n))
  elif "$" not in raw: paths.add(raw)
 missing=[p for p in sorted(paths) if not (d/"ims"/p).is_file()]
 if missing: raise ValueError("Android.mk inputs missing: "+", ".join(missing))
 return {"checked":len(paths),"missing":[]}
def report(path,status="PASS"):
 r=json.loads(reg(path).read_text(encoding="utf-8"))
 if not isinstance(r,dict) or r.get("status")!=status: raise ValueError(f"report not {status}: {path}")
 return r
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--source-root",type=Path,required=True); p.add_argument("--producer-work",type=Path,required=True)
 p.add_argument("--compat-root",type=Path,default=ROOT); p.add_argument("--report",type=Path,required=True)
 p.add_argument("--ims-receipt",type=Path); a=p.parse_args(argv)
 root,work,compat=a.source_root.resolve(),a.producer_work.resolve(),a.compat_root.resolve(); d=root/DEV
 r={"schema_version":1,"status":"BLOCKED","runtime_validated":False,"android_build_run":False,
 "native_compile":"PENDING_USER_ANDROID_BUILD","checks":{},"errors":[]}
 try:
  if not all(x.is_dir() for x in (root,work,compat)): raise ValueError("source-root/producer-work/compat-root must exist")
  r["checks"]["manifest_copy_rows"]=copies(root,compat)
  if r["checks"]["manifest_copy_rows"]["failed"]: raise ValueError("payload manifest copy checks failed")
  r["checks"]["source_integration"]=source(root); r["checks"]["make_payload_paths"]=makepaths(root); r["checks"]["native_sve"]=native(root)
  dest={n:reg(d/rel) for n,rel in APK.items()}; artifacts={}
  for n,pth in dest.items():
   out=reg(work/"outputs"/OUT[n])
   if sha(out)!=sha(pth): raise ValueError(f"producer output differs from staged {n}")
   artifacts[n]={"sha256":sha(pth),"size":pth.stat().st_size}
  receipts=module(compat,"source_verified_receipt")
  jobs=[("imsservice",a.ims_receipt or work/"reports/ims-lg3-source-verified.json",["imsservice-source-verified","bv1-source-verified","lg3-source-verified"]),
  ("sveservice",work/"reports/sveservice-sv1-source-verified.json",["sveservice-sv1-source-verified"]),
  ("EpdgService",work/"reports/EpdgService-lg2-source-verified.json",["epdgservice-ec2-source-verified","epdgservice-lg2-source-verified"])]
  verified={}
  for n,path,chain in jobs: verified[n]=receipts.verify_source_verified_input(path,dest[n],chain[-1],chain)
  r["checks"]["source_verified_apks"]=verified
  uw=report(work/"reports/UnifiedWFC-uw1.json"); uout=reg(work/"outputs/UnifiedWFC-uw1-unsigned.apk")
  contract=json.loads(reg(compat/"devices/m11q/unifiedwfc-sim-mobility-contract.json").read_text(encoding="utf-8"))
  check_uw1_identity(uw,contract)
  if uw.get("output_apk_sha256")!=sha(uout) or sha(uout)!=sha(dest["UnifiedWFC"]): raise ValueError("UW1 report/output mismatch")
  r["checks"]["uw1"]={"status":"PASS","output_sha256":sha(uout)}
  er=report(work/"reports/er1.json")
  if er.get("transformation_id")!="ER1-private-crypto-namespace": raise ValueError("ER1 identity mismatch")
  reported={x.get("output_name"):x.get("output_sha256") for x in er.get("outputs",[])}; ercheck={}
  for n,rel in ERIS.items():
   staged=reg(d/rel); out=reg(work/"outputs/er1"/n)
   if sha(staged)!=sha(out) or reported.get(n)!=sha(staged): raise ValueError(f"ER1 report/output mismatch: {n}")
   ercheck[n]={"sha256":sha(staged),"size":staged.stat().st_size}
  r["checks"]["er1"]={"status":"PASS","outputs":ercheck}
  r["checks"]["audiofw"]=audio(work/"stock-inputs/system/lib/libAudioFWInterface.so",
   d/"ims/proprietary/app/sveservice/lib/arm/libAudioFWInterface.so",work/"reports/audiofw.json")
  r["artifacts"]=artifacts; r["summary"]={"copy_rows_checked":40,"generated_apks":4,"eris_outputs":3,"audiofw_outputs":1}
  r["status"]="READY_FOR_USER_BUILD"
 except Exception as e: r["errors"].append(str(e))
 a.report.parent.mkdir(parents=True,exist_ok=True)
 a.report.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 print(json.dumps({"status":r["status"],"checks":len(r["checks"]),"errors":len(r["errors"]),"report":str(a.report)},sort_keys=True))
 return 0 if r["status"]=="READY_FOR_USER_BUILD" else 1
if __name__=="__main__": raise SystemExit(main())
