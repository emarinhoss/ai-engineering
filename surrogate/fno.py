"""1D Fourier neural operator ensemble (Task 4c, docs/specs/task4c_operator_profiles.md).

Maps (theta1, theta2) to a profile on a fixed grid of n points in s = [0, 1]. Input channels on the
grid: s, theta1, theta2 (the angles as constant channels). A Fourier layer adds two paths, a
spectral convolution that keeps only the lowest `modes` Fourier modes (one complex
width x width matrix per mode) and a pointwise linear map (Li et al. 2021, "Fourier neural
operator for parametric partial differential equations"). The profile is not periodic, so the
grid is padded with zeros before the Fourier layers and cropped after them.
Five members from seeds 0 to 4; the ensemble mean is the prediction, the spread the uncertainty.
"""
import torch
from torch import nn

WIDTH, MODES, LAYERS, PAD = 32, 16, 4, 32
STEPS, LR, WEIGHT_DECAY, MEMBERS = 3000, 3e-3, 1e-4, 5


class SpectralConv1d(nn.Module):
    """h (B, width, n) -> irfft( W_k @ rfft(h)_k for the lowest `modes` k, zero above )."""

    def __init__(self, width, modes):
        super().__init__()
        self.modes = modes
        scale = 1.0 / (width * width)
        self.w_re = nn.Parameter(scale * torch.randn(width, width, modes))
        self.w_im = nn.Parameter(scale * torch.randn(width, width, modes))

    def forward(self, h):
        H = torch.fft.rfft(h)                                          # (B, width, n // 2 + 1)
        W = torch.complex(self.w_re, self.w_im)                         # (in, out, modes)
        out = torch.zeros_like(H)
        out[:, :, :self.modes] = torch.einsum("bim,iom->bom", H[:, :, :self.modes], W)
        return torch.fft.irfft(out, n=h.shape[-1])


class FNO1d(nn.Module):
    def __init__(self, in_channels=3, width=WIDTH, modes=MODES, layers=LAYERS, pad=PAD):
        super().__init__()
        self.pad = pad
        self.lift = nn.Linear(in_channels, width)
        self.spectral = nn.ModuleList([SpectralConv1d(width, modes) for _ in range(layers)])
        self.pointwise = nn.ModuleList([nn.Conv1d(width, width, 1) for _ in range(layers)])
        self.project = nn.Sequential(nn.Linear(width, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, a):
        """a (B, n, in_channels) -> (B, n)."""
        h = self.lift(a).permute(0, 2, 1)                              # (B, width, n)
        h = nn.functional.pad(h, (0, self.pad))                         # zeros after the last point
        for i, (spec, pw) in enumerate(zip(self.spectral, self.pointwise)):
            h = spec(h) + pw(h)
            if i < len(self.spectral) - 1:
                h = nn.functional.gelu(h)
        h = h[:, :, :h.shape[-1] - self.pad].permute(0, 2, 1)          # crop, (B, n, width)
        return self.project(h).squeeze(-1)


def grid_input(X, n):
    """X (B, 2) in [0, 1] -> (B, n, 3) channels s, theta1, theta2."""
    X = torch.as_tensor(X, dtype=torch.float32)
    s = torch.linspace(0.0, 1.0, n).expand(X.shape[0], n)
    return torch.stack([s, X[:, :1].expand(-1, n), X[:, 1:].expand(-1, n)], dim=-1)


class FNOEnsemble:
    def __init__(self, members=MEMBERS, steps=STEPS, lr=LR, weight_decay=WEIGHT_DECAY):
        self.members, self.steps, self.lr, self.weight_decay = members, steps, lr, weight_decay

    def fit(self, X, Y):
        """X (B, 2) unit-square inputs, Y (B, n) scaled targets. Full-batch MSE, AdamW."""
        Y = torch.as_tensor(Y, dtype=torch.float32)
        a = grid_input(X, Y.shape[1])
        self.nets = []
        for seed in range(self.members):
            torch.manual_seed(seed)
            net = FNO1d()
            opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=self.weight_decay)
            for _ in range(self.steps):
                opt.zero_grad()
                loss = ((net(a) - Y) ** 2).mean()
                loss.backward()
                opt.step()
            self.nets.append(net)
        self.n = Y.shape[1]
        return self

    def predict(self, Xs):
        """-> mean (m, n), variance between members (m, n), as float64 tensors."""
        a = grid_input(Xs, self.n)
        with torch.no_grad():
            P = torch.stack([net(a) for net in self.nets]).double()     # (members, m, n)
        return P.mean(0), P.var(0, unbiased=True).clamp(min=1e-12)
