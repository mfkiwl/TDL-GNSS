import torch
import torch.nn as nn


class StandardizeLayer(nn.Module):
    def __init__(self, mean, std):
        super(StandardizeLayer, self).__init__()
        self.mean = nn.Parameter(mean, requires_grad=False)
        self.std = nn.Parameter(std, requires_grad=False)

    def forward(self, x):
        return (x - self.mean) / self.std

class DeStandardizeLayer(nn.Module):
    def __init__(self, mean, std):
        super(DeStandardizeLayer, self).__init__()
        self.mean = nn.Parameter(mean, requires_grad=False)
        self.std = nn.Parameter(std, requires_grad=False)

    def forward(self, x):
        return  x * self.std+self.mean


class BiasNet(nn.Module):
    def __init__(self, imean=0, istd=1, omean=0, ostd=1):
        super().__init__()
        self.seq = torch.nn.Sequential(
            StandardizeLayer(imean, istd),
            nn.Linear(3, 64),
            torch.nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Linear(64,128),
            torch.nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Linear(128, 1),
            DeStandardizeLayer(omean,ostd)
        )


    def forward(self, x):
        x = self.seq(x)
        return x


class WeightNet(nn.Module):
    def __init__(self, imean=torch.tensor([0,0,0],dtype=torch.float64), istd=torch.tensor([1,1,1],dtype=torch.float64)):
        super().__init__()
        self.seq = torch.nn.Sequential(
            StandardizeLayer(imean, istd),
            nn.Linear(3, 64),
            #torch.nn.BatchNorm1d(64),
            nn.Sigmoid(),
            nn.Linear(64,128),
            #torch.nn.BatchNorm1d(128),
            nn.Sigmoid(),
            nn.Linear(128, 64),
            nn.Sigmoid(),
            nn.Linear(64,1),
            nn.Sigmoid()
        )


    def forward(self, x):
        x = self.seq(x) * 10
        x = torch.clamp(x,min=0,max = 10)
        return x