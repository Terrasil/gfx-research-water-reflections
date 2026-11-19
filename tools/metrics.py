import numpy as np

def masks(pos, normal, ref_diag):
    cls=ref_diag[...,2].astype(int)
    return dict(valid=cls>0, sky=cls==1, offscreen=cls==2, hidden=cls==3, visible=cls==4)

def summarize(signal, diag, reference, region, refdiag):
    valid = region["valid"]
    predicted = diag[...,0]>0
    correct = predicted & (diag[...,0]==refdiag[...,0]) & (np.abs(diag[...,1]-refdiag[...,1])<=refdiag[...,3])
    good = correct & region["visible"]
    mse = ((signal-reference)**2).mean(axis=-1)
    def ratio(a,b):
        return float(a/b) if b else None
    result = dict(rgb_rmse=float(np.sqrt(mse[valid].mean())), visible_recall=ratio(good.sum(),region["visible"].sum()),
                  precision=ratio((correct & valid).sum(),(predicted & valid).sum()),
                  sky_false_positive=ratio((predicted & region["sky"]).sum(),region["sky"].sum()),
                  wrong_hits_per_receiver=ratio((predicted & ~correct & valid).sum(),valid.sum()),
                  visible_correct_hits=int(good.sum()), predicted_hits=int((predicted & valid).sum()),
                  probes_per_pixel=float(diag[...,2][valid].mean()), fallback_per_pixel=float(diag[...,3][valid].mean()))
    for name,mask in region.items():
        result[name+"_pixels"] = int(mask.sum())
        result[name+"_rgb_rmse"] = float(np.sqrt(mse[mask].mean())) if mask.any() else None
    return result

def pixel_error(signal, reference):
    return np.sqrt(np.mean((signal-reference)**2,axis=-1))

def reference_check(reference, region, shifts, refdiag, scene):
    if not region["valid"].any(): raise ValueError("No reflecting receivers")
    if scene==4 and not np.array_equal(region["valid"],region["sky"]): raise ValueError("Empty-scene reference failed")
    if scene!=4 and not region["visible"].any(): raise ValueError("No recoverable geometry in reflection scene")
    return {}

def method_check(signal, diag, reference, region, scene):
    if scene==4 and ((diag[...,0][region["valid"]]!=0).any() or not np.allclose(signal[region["valid"]],reference[region["valid"]],atol=1e-6)):
        raise ValueError("Empty-environment control failed")

def region_image(region):
    colors=np.array([[0,0,0],[120,160,220],[240,160,70],[200,70,80],[60,175,115]],dtype="uint8")
    group=region["sky"].astype(int)+region["offscreen"]*2+region["hidden"]*3+region["visible"]*4
    return colors[group]
