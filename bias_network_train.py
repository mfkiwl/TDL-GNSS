import torch
import pyrtklib as prl
import rtk_util as util
import json
import sys
import numpy as np
import pandas as pd
import pymap3d as p3d
from model import BiasNetTest
from torch.nn import HuberLoss,MSELoss
import matplotlib.pyplot as plt
from tqdm import tqdm
import os


DEVICE = 'cuda'


try:
    config = sys.argv[1]
except:
    config = "config/bias/klt3_train.json"

with open(config) as f:
    conf = json.load(f)

mode = conf['mode']
if mode not in ['train','predict']:
    raise RuntimeError("%s is not a valid option"%mode)

os.makedirs(conf['model'],exist_ok=True)
result = config.split("/")[-1].split(".json")[0]
result_path = "result/bias/"+result
os.makedirs(result_path,exist_ok=True)



obs,nav,sta = util.read_obs(conf['obs'],conf['eph'])
prl.sortobs(obs)
obss = util.split_obs(obs)

tmp = []

if conf.get("gt",None):
    gt = pd.read_csv(conf['gt'],skiprows = 30, header = None,sep =' +', skipfooter = 4, error_bad_lines=False, engine='python')
    gt[0] = gt[0]+18 # leap seconds
    gts = []

# filter and normalize
gather_data = []
for o in obss:
    t = o.data[0].time
    t = t.time+t.sec
    if t > conf['start_time'] and (conf['end_time'] == -1 and 1 or t < conf['end_time']):
        tmp.append(o)
        if conf.get("gt",None):
            gt_row = gt.loc[(gt[0]-t).abs().argmin()]
            gts.append([gt_row[3]+gt_row[4]/60+gt_row[5]/3600,gt_row[6]+gt_row[7]/60+gt_row[8]/3600,gt_row[9]])

            
        ret = util.get_ls_pnt_pos(o,nav)
        if not ret['status']:
            continue
        rs = ret['data']['eph']
        dts = ret['data']['dts']
        sats = ret['data']['sats']
        exclude = ret['data']['exclude']
        prs = ret['data']['prs']
        resd = np.array(ret['data']['residual'])
        SNR = np.array(ret['data']['SNR'])
        azel = np.delete(np.array(ret['data']['azel']).reshape((-1,2)),exclude,axis=0)
        gather_data.append(np.hstack([SNR.reshape(-1,1),azel[:,1:],resd]))

        if conf.get("gt",None):
            gt_row = gt.loc[(gt[0]-t).abs().argmin()]
            gts.append([gt_row[3]+gt_row[4]/60+gt_row[5]/3600,gt_row[6]+gt_row[7]/60+gt_row[8]/3600,gt_row[9]])

norm_data = np.vstack(gather_data)
imean = norm_data.mean(axis=0)
istd = norm_data.std(axis=0)

print(f"preprocess done, mean:{imean}, std:{istd}")

net = BiasNetTest(torch.tensor(imean,dtype=torch.float32),torch.tensor(istd,dtype=torch.float32))
net.double()
net = net.to(DEVICE)


obss = tmp

pos_errs = []


opt = torch.optim.Adam(net.parameters(),lr = 0.01)
epoch = conf.get('epoch',500)
batch = conf.get('batch',128)
lossFn = MSELoss(reduction='sum')
vis_loss = []


for k in range(epoch):
    loss = 0
    with tqdm(range(len(obss)),desc=f"Epoch {k+1}") as t:
        for i in t:
            o = obss[i]
            if conf.get("gt",None):
                gt_row = gts[i]
            ret = util.get_ls_pnt_pos(o,nav)
            if not ret['status']:
                continue
            pos_err_src = p3d.ecef2enu(*ret['pos'][:3],gt_row[0],gt_row[1],gt_row[2])
            rs = ret['data']['eph']
            dts = ret['data']['dts']
            sats = ret['data']['sats']
            exclude = ret['data']['exclude']
            prs = ret['data']['prs']
            resd = np.array(ret['data']['residual'])
            SNR = np.array(ret['data']['SNR'])
            azel = np.delete(np.array(ret['data']['azel']).reshape((-1,2)),exclude,axis=0)
            in_data = torch.tensor(np.hstack([SNR.reshape(-1,1),azel[:,1:],resd]),dtype=torch.float32).to(DEVICE)
            predict_bias = net(in_data).squeeze()
            #print(predict_weight)
            select_sats = list(np.delete(np.array(sats),exclude))

            ret = util.get_ls_pnt_pos_torch(o,nav,b = predict_bias.unsqueeze(1),p_init=ret['pos'])
            
            
            gt_ecef = p3d.geodetic2ecef(*gt_row)
            enu = p3d.ecef2enu(*ret['pos'][:3],gt_row[0],gt_row[1],gt_row[2])
            epoch_loss = torch.norm(torch.hstack(enu[:3]))
            #epoch_loss = lossFn(ret['pos'][:3],torch.tensor(gt_ecef).to(DEVICE))
            loss += epoch_loss
            t.set_postfix({'epoch loss':epoch_loss.item()})
            #torch.norm(ret['pos'][:3]-torch.tensor(gt_ecef).to(DEVICE))
            # pos_err_pre = p3d.ecef2enu(*ret['pos'][:3],gt_row[0],gt_row[1],gt_row[2])
            # pos_errs.append([np.linalg.norm(pos_err_src[:2]),np.linalg.norm(pos_err_pre[:2])])
        opt.zero_grad()
        loss.backward()
        opt.step()
        print(loss.item()/len(obss))
        vis_loss.append(loss.item())
torch.save(net.state_dict(),conf['model']+"/biasnet_3d.pth")
vis_loss = np.array(vis_loss)
plt.plot(vis_loss)
plt.savefig(result_path+"/loss.png")
np.savetxt(result_path+"/loss.csv",vis_loss.reshape(-1,1))