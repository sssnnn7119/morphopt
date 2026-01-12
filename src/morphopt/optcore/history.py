import csv
import numpy as np
import torch
from .baseobject import BaseObject

class History(BaseObject):
    """
    A class to record the information of the optimization process.
    """

    def __init__(self):
        self.data: dict[str, np.ndarray] = {}
        self.iteration: int = 0
    
    def initialize(self) -> None:
        self.iteration = 0
        self.data = {}

    def append(self, name: str, value: any) -> None:
        """
        Append a value to the history data.
        """
        if value is None:
            return 
        
        # Helper to safely convert torch tensors to numpy
        def to_numpy(val):
            if isinstance(val, torch.Tensor):
                return val.detach().cpu().numpy()
            return val

        if isinstance(value, list):
            value = [to_numpy(v) for v in value]
        else:
            value = to_numpy(value)
            
        new_val = np.array(value)
        if name not in self.data:
            if new_val.ndim == 0:
                # Scalar -> 1D array
                self.data[name] = new_val.reshape(1)
            else:
                # Array -> (1, ...) array
                self.data[name] = new_val.reshape(1, *new_val.shape)
        else:
            # stack on the first axis (0)
            target_shape = (1, *new_val.shape)
            self.data[name] = np.concatenate((self.data[name], new_val.reshape(target_shape)), axis=0)
            
        if name == 'objective':
            self.iteration = len(self.data[name])

    @property
    def history_objective(self):
        return self.data.get('objective', np.array([]))
    
    @history_objective.setter
    def history_objective(self, val):
        self.data['objective'] = np.array(val)
        self.iteration = len(val)

    @property
    def history_time(self):
        return self.data.get('time', np.array([]))
    
    @history_time.setter
    def history_time(self, val):
        self.data['time'] = np.array(val)

    @property
    def history_num_elements(self):
        return self.data.get('num_elements', np.array([]))
    
    @history_num_elements.setter
    def history_num_elements(self, val):
        self.data['num_elements'] = np.array(val)

    @property
    def history_num_nodes(self):
        return self.data.get('num_nodes', np.array([]))

    @history_num_nodes.setter
    def history_num_nodes(self, val):
        self.data['num_nodes'] = np.array(val)

    @property
    def history_deformation(self):
        return self.data.get('deformation', np.array([]))
    
    @history_deformation.setter
    def history_deformation(self, val):
        self.data['deformation'] = np.array(val)

    @property
    def history_metrics(self):
        return self.data.get('metrics', np.array([]))
    
    @history_metrics.setter
    def history_metrics(self, val):
        self.data['metrics'] = np.array(val)

    def save(self, foldpath: str, *args, **kwargs) -> None:
        """
        Save the history to a CSV file.
        CSV format:
        - Row 1: Column headers (iteration, objective, T0, T1, ..., U0-0, U0-1, ..., UdF0-0-0, UdF0-0-1, ...)
        - Row 2+: Data records
        """
        filepath = foldpath + '/history_record.csv'

        # Determine keys and order
        # Fixed order for known keys, then others
        standard_keys = ['objective', 'metrics', 'time', 'num_elements', 'num_nodes', 'deformation']
        other_keys = [k for k in self.data.keys() if k not in standard_keys]
        all_keys = standard_keys + sorted(other_keys)
        
        # Filter keys that actually exist
        target_keys = [k for k in all_keys if k in self.data and len(self.data[k]) > 0]
        
        # Prepare headers
        headers = ['iteration']
        key_dims = {} # Store dimensions for each key to handle flattening
        
        for k in target_keys:
            arr = self.data[k]
            # check shape of the content (excluding iteration dim)
            item_shape = arr.shape[1:]
            
            if len(item_shape) == 0:
                # Scalar per iteration
                headers.append(k)
                key_dims[k] = 0
            elif len(item_shape) == 1:
                # 1D array per iteration
                for i in range(item_shape[0]):
                    if k == 'time':
                         headers.append(f'T{i}')
                    else:
                         headers.append(f'{k}_{i}')
                key_dims[k] = 1
            else:
                # Multi-dim array per iteration - flatten
                flat_size = np.prod(item_shape)
                if k == 'deformation':
                    if len(item_shape) == 2:
                        for r in range(item_shape[0]):
                            for c in range(item_shape[1]):
                                headers.append(f'U{r}-{c}')
                    else:
                        for i in range(flat_size):
                             headers.append(f'{k}_{i}')
                else:
                    for i in range(flat_size):
                        headers.append(f'{k}_{i}')
                key_dims[k] = item_shape

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            
            # Write rows
            max_len = 0
            for k in target_keys:
                max_len = max(max_len, len(self.data[k]))
            
            for i in range(max_len):
                row = [i+1]
                for k in target_keys:
                    arr = self.data[k]
                    if i < len(arr):
                        val = arr[i]
                        if key_dims[k] == 0:
                            row.append(val)
                        else:
                            # Flatten
                            row.extend(val.flatten().tolist())
                    else:
                        # Pad with empty
                        shape = key_dims[k]
                        if shape == 0:
                            size = 1
                        elif isinstance(shape, int):
                            size = shape
                        else:
                            size = np.prod(shape)
                        row.extend([''] * size)
                
                # Formatting
                formatted_row = []
                for idx, val in enumerate(row):
                    if idx == 0:
                        formatted_row.append(val)
                    elif isinstance(val, (float, np.floating)):
                        formatted_row.append(f"{val:.4e}")
                    else:
                        formatted_row.append(val)
                writer.writerow(formatted_row)

    def load(self, foldpath: str, iteration: int = None) -> None:
        """
        Load the history from a CSV file.
        """
        filepath = foldpath + '/history_record.csv'
        self.initialize()
        
        try:
            with open(filepath, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                try:
                    headers = next(reader)
                except StopIteration:
                    return

                col_map = [] 
                
                for h in headers:
                    if h == 'iteration':
                        col_map.append(None)
                    elif h == 'objective':
                        col_map.append(('objective', None))
                    elif h == 'num_elements':
                        col_map.append(('num_elements', None))
                    elif h == 'num_nodes':
                        col_map.append(('num_nodes', None))
                    elif h.startswith('T') and h[1:].isdigit():
                        col_map.append(('time', int(h[1:])))
                    elif h.startswith('U') and '-' in h:
                        col_map.append(('deformation', h))
                    else:
                        if '_' in h:
                            parts = h.rsplit('_', 1)
                            if parts[1].isdigit():
                                col_map.append((parts[0], int(parts[1])))
                            else:
                                col_map.append((h, None))
                        else:
                            col_map.append((h, None))

                rows = list(reader)
        except FileNotFoundError:
            return

        if not rows:
            return

        # Temporary lists
        data_lists = {
            'objective': [],
            'time': [],
            'num_elements': [],
            'num_nodes': [],
            'deformation': [],
            'metrics': []
        }
        
        # Helper to classify scalars vs arrays
        # Fixed classifications
        scalar_keys = {'objective', 'num_elements', 'num_nodes'}
        
        # Analyze col_map to classify other keys
        # Collect subs for each key to determine if it's scalar or array
        key_subs = {} 
        for item in col_map:
            if item is None: continue
            k, sub = item
            if k not in key_subs: key_subs[k] = set()
            key_subs[k].add(sub)
            
            # Ensure key is in data_lists
            if k not in data_lists:
                data_lists[k] = []

        # Determine which are scalars (all subs are None)
        # Exception: deformation is always array (sub like U0-0)
        # Exception: time is always array (sub 0, 1...)
        
        for k, subs in key_subs.items():
            if k in scalar_keys: continue
            if k == 'deformation' or k == 'time': continue
            
            if len(subs) == 1 and list(subs)[0] is None:
                scalar_keys.add(k)


        # Determine shape for deformation
        def_indices = [h for h in headers if h.startswith('U') and '-' in h]
        max_r, max_c = 0, 0
        if def_indices:
            for h in def_indices:
                parts = h.replace('U','').split('-')
                if len(parts) == 2:
                    try:
                       r, c = int(parts[0]), int(parts[1])
                       max_r = max(max_r, r)
                       max_c = max(max_c, c)
                    except: pass
            def_shape = (max_r+1, max_c+1)
        else:
            def_shape = None

        for row in rows:
            if not row: continue
            
            # Init row data container
            row_data = {}
            for k in data_lists:
                if k in scalar_keys:
                    row_data[k] = None
                else:
                    row_data[k] = {}

            for i, val_str in enumerate(row):
                if i >= len(col_map) or col_map[i] is None: continue
                if val_str == '': continue
                
                try: val = float(val_str)
                except: val = val_str # Fallback strings
                
                key, sub = col_map[i]
                
                if key in scalar_keys:
                    if key in ['num_elements', 'num_nodes']:
                        try: row_data[key] = int(val)
                        except: row_data[key] = val
                    else:
                        row_data[key] = val
                else:
                    # Array type
                    if key == 'deformation':
                         parts = sub.replace('U','').split('-')
                         r, c = int(parts[0]), int(parts[1])
                         row_data[key][(r,c)] = val
                    else:
                         idx = sub if sub is not None else 0
                         row_data[key][idx] = val
            
            # Convert row_data to list elements
            for k, v in row_data.items():
                if k in scalar_keys:
                    if v is not None:
                         data_lists[k].append(v)
                    # If None, it means missing value for this row, we skip or handle?
                    # Current logic skips append, which might misalign rows if data is sparse?
                    # But history usually dense. 
                    # Existing code also did: if v is not None: append.
                elif k == 'deformation':
                    if def_shape and v:
                        d_mat = np.zeros(def_shape)
                        for (r,c), val in v.items():
                            d_mat[r, c] = val
                        data_lists[k].append(d_mat)
                    elif v:
                         pass
                else:
                    # Generic Array
                    if v:
                        max_idx = max(v.keys()) if all(isinstance(x, int) for x in v.keys()) else len(v)-1
                        vec = [v.get(x, 0.0) for x in range(max_idx+1)]
                        data_lists[k].append(vec)
        
        # Convert to arrays

        for k, v in data_lists.items():
            if v:
                self.data[k] = np.array(v)

        # Iteration slice
        if iteration is not None:
            for k in self.data:
                self.data[k] = self.data[k][:iteration]
        
        if 'objective' in self.data:
            self.iteration = len(self.data['objective'])
