"""Les instances : fichiers du dossier `instances/` et fichiers envoyés au serveur."""

import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from solvers.instance import Instance, load_instance, load_instance_from_bytes


def _num(x):
    """Entier si la valeur est entière (82.0 -> 82), pour un JSON propre."""
    x = float(x)
    return int(x) if x.is_integer() else x


class InstanceStore:
    def __init__(self, directory: Path, max_uploads: int = 20):
        self.directory = Path(directory)
        self.max_uploads = max_uploads
        self._lock = threading.Lock()
        self._library: dict[str, Instance] = {}  # id -> instance déjà lue
        self._uploads: "OrderedDict[str, Instance]" = OrderedDict()

    # -- fichiers du dépôt : on ne sert que ceux de la liste, jamais un chemin donné par le client
    def _paths(self) -> dict[str, Path]:
        return {p.stem: p for p in sorted(self.directory.rglob("*.vrp"))}

    def get(self, instance_id: str) -> tuple[Instance, str] | None:
        """(instance, source) ou None si elle n'existe pas. source = "library" ou "upload"."""
        with self._lock:
            if instance_id in self._uploads:
                return self._uploads[instance_id], "upload"
            if instance_id in self._library:
                return self._library[instance_id], "library"
            path = self._paths().get(instance_id)
            if path is None:
                return None
            self._library[instance_id] = load_instance(path)
            return self._library[instance_id], "library"

    def add_upload(self, data: bytes, filename: str) -> str:
        inst = load_instance_from_bytes(data, filename)  # lève ValueError si le fichier est invalide
        with self._lock:
            instance_id = f"up-{uuid.uuid4().hex[:8]}"
            self._uploads[instance_id] = inst
            while len(self._uploads) > self.max_uploads:
                self._uploads.popitem(last=False)
        return instance_id

    # -- JSON
    def summaries(self) -> list[dict]:
        out = []
        for instance_id in self._paths():
            inst, source = self.get(instance_id)
            out.append(_summary(instance_id, inst, source))
        with self._lock:
            uploads = list(self._uploads.items())
        out += [_summary(i, inst, "upload") for i, inst in uploads]
        return out

    def detail(self, instance_id: str) -> dict | None:
        found = self.get(instance_id)
        if found is None:
            return None
        inst, source = found
        best = None
        if inst.bks is not None or inst.best_routes:
            best = {"cost": _num(inst.bks) if inst.bks is not None else None, "routes": inst.best_routes}
        return {
            "id": instance_id,
            "name": inst.name,
            "source": source,
            "n_clients": inst.n - 1,
            "capacity": inst.capacity,
            "n_vehicles": inst.n_vehicles,
            "edge_weight_type": inst.edge_weight_type,
            "coords": [[_num(x), _num(y)] for x, y in inst.coords],
            "demand": [int(d) for d in inst.demand],
            "best_known": best,
        }


def _summary(instance_id: str, inst: Instance, source: str) -> dict:
    return {
        "id": instance_id,
        "name": inst.name,
        "n_clients": inst.n - 1,
        "capacity": inst.capacity,
        "n_vehicles": inst.n_vehicles,
        "best_known_cost": _num(inst.bks) if inst.bks is not None else None,
        "has_best_known_routes": bool(inst.best_routes),
        "source": source,
    }
