import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
import json

SAMPLE_RATE = 100
SEGMENT_LEN = 140  # taille réelle du dataset ecg.csv
BATCH_SIZE  = 64
EPOCHS      = 10
LR          = 1e-3

if torch.backends.mps.is_available():
    DEVICE = 'mps'
elif torch.cuda.is_available():
    DEVICE = 'cuda'
else:
    DEVICE = 'cpu'

print(f"Device utilisé : {DEVICE}")
MODEL_PATH = 'heartaim_stress_model.pt'

# ── Dataset ──────────────────────────────────────────
class ECGStressDataset(Dataset):
    def __init__(self, signals, labels):
        self.X = torch.tensor(signals, dtype=torch.float32)
        self.y = torch.tensor(labels,  dtype=torch.long)
    def __len__(self):
        return len(self.X)
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

# ── Modèle 1D-CNN ────────────────────────────────────
class ECGStressCNN(nn.Module):
    def __init__(self, num_classes=2, input_len=140):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=5, padding=2),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.MaxPool1d(2), nn.Dropout(0.2),

            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64), nn.ReLU(),
            nn.MaxPool1d(2), nn.Dropout(0.2),

            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128), nn.ReLU(),
            nn.MaxPool1d(2), nn.Dropout(0.3),
        )

        # Calculer automatiquement la taille du flatten
        dummy = torch.zeros(1, 1, input_len)
        flat_size = self._get_flat_size(dummy)

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat_size, 128), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(128, 64),        nn.ReLU(),
            nn.Linear(64, num_classes)
        )

    def _get_flat_size(self, x):
        with torch.no_grad():
            out = self.features(x)
        return out.view(1, -1).shape[1]

    def forward(self, x):
        if x.dim() == 2:
            x = x.unsqueeze(1)
        return self.classifier(self.features(x))

# ── Chargement dataset ────────────────────────────────
def load_data():
    print("Chargement ECG dataset...")
    from sklearn.preprocessing import LabelEncoder
    import urllib.request
    import pandas as pd

    url = "https://storage.googleapis.com/download.tensorflow.org/data/ecg.csv"
    print("Téléchargement ecg.csv...")
    urllib.request.urlretrieve(url, "ecg.csv")

    df    = pd.read_csv("ecg.csv", header=None)
    X_raw = df.iloc[:500, :-1].values.astype(np.float32)
    y_raw = df.iloc[:500, -1].values.astype(int)

    # Taille réelle des signaux
    actual_len = X_raw.shape[1]
    print(f"Taille signal détectée : {actual_len}")

    signals, raw_labels = [], []
    for i in range(len(X_raw)):
        ecg = X_raw[i]
        ecg = (ecg - np.mean(ecg)) / (np.std(ecg) + 1e-8)
        signals.append(ecg)
        raw_labels.append('calm' if y_raw[i] == 1 else 'stress')

    le        = LabelEncoder()
    label_arr = le.fit_transform(raw_labels)
    label_map = {str(i): str(c) for i, c in enumerate(le.classes_)}

    with open('label_mapping.json', 'w') as f:
        json.dump(label_map, f, indent=2)

    print(f"Classes: {label_map} | Samples: {len(signals)}")
    return np.array(signals), label_arr, len(le.classes_), label_map, actual_len

# ── Entraînement ─────────────────────────────────────
def train():
    signals, labels, num_classes, label_map, input_len = load_data()

    X_train, X_val, y_train, y_val = train_test_split(
        signals, labels, test_size=0.2, random_state=42, stratify=labels
    )

    train_loader = DataLoader(ECGStressDataset(X_train, y_train),
                              batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(ECGStressDataset(X_val, y_val),
                              batch_size=BATCH_SIZE)

    model     = ECGStressCNN(num_classes=num_classes, input_len=input_len).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = nn.CrossEntropyLoss()
    best_acc  = 0

    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss, correct = 0, 0
        for X, y in train_loader:
            X, y = X.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad()
            out  = model(X)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            correct    += (out.argmax(1) == y).sum().item()
        scheduler.step()

        model.eval()
        val_correct = 0
        with torch.no_grad():
            for X, y in val_loader:
                X, y = X.to(DEVICE), y.to(DEVICE)
                out = model(X)
                val_correct += (out.argmax(1) == y).sum().item()

        t_acc = correct     / len(X_train) * 100
        v_acc = val_correct / len(X_val)   * 100
        print(f"Epoch {epoch:02d}/{EPOCHS} | Loss:{total_loss/len(train_loader):.4f} | Train:{t_acc:.1f}% | Val:{v_acc:.1f}%")

        if v_acc > best_acc:
            best_acc = v_acc
            torch.save({
                'model_state':   model.state_dict(),
                'num_classes':   num_classes,
                'label_mapping': label_map,
                'sample_rate':   SAMPLE_RATE,
                'segment_len':   input_len
            }, MODEL_PATH)
            print(f"  ✓ Sauvegarde ({v_acc:.1f}%)")

    print(f"Termine. Meilleure accuracy: {best_acc:.1f}%")

# ── Inference ────────────────────────────────────────
class StressPredictor:
    def __init__(self, model_path=MODEL_PATH):
        ckpt = torch.load(model_path, map_location='cpu')
        self.segment_len   = ckpt['segment_len']
        self.label_mapping = ckpt['label_mapping']
        self.model = ECGStressCNN(
            num_classes=ckpt['num_classes'],
            input_len=self.segment_len
        )
        self.model.load_state_dict(ckpt['model_state'])
        self.model.eval()

    def predict(self, ecg_segment):
        seg = np.array(ecg_segment[:self.segment_len], dtype=np.float32)
        if len(seg) < self.segment_len:
            seg = np.pad(seg, (0, self.segment_len - len(seg)))
        seg = (seg - seg.mean()) / (seg.std() + 1e-8)
        x   = torch.tensor(seg).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0]
            pred  = probs.argmax().item()
        state = self.label_mapping[str(pred)]
        return {
            'state':      state.upper(),
            'confidence': round(float(probs[pred]), 3),
            'speed':      {'calm': 1.0, 'focus': 0.6, 'stress': 0.2}.get(state, 0.6),
            'stress':     {'calm': 20,  'focus': 50,  'stress': 80}.get(state, 50)
        }

if __name__ == "__main__":
    train()