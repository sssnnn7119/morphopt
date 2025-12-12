import csv
import numpy as np

class History:
    """
    A class to record the information of the optimization process.
    """

    def __init__(self):
        self.history_objective: list[float] = []
        """
        The history of the objective function values.
        """
        self.history_time: list[list[float]] = []
        """
        The history of the time taken for each iteration.
        """
        
        self.history_deformation: list = []
        """
        The history of the deformation values.
        """

        self.history_num_elements: list[int] = []
        """
        The history of the number of elements.
        """
        self.history_num_nodes: list[int] = []
        """
        The history of the number of nodes.
        """
        
        self.iteration: int = 0
        """
        The current iteration number.
        """

    def save(self, path: str) -> None:
        """
        Save the history to a file.
        """
        np.savetxt(path + '/history_objective.txt', self.history_objective, delimiter=',')
        np.savetxt(path + '/history_time.txt', self.history_time, delimiter=',')
        np.savetxt(path + '/iteration.txt', [self.iteration], delimiter=',')
        np.save(path + '/history_deformation.npy', self.history_deformation)
        
    def load(self, path: str) -> None:
        """
        Load the history from a file.
        """
        self.history_objective = np.loadtxt(path + '/history_objective.txt', delimiter=',').tolist()
        self.history_time = np.loadtxt(path + '/history_time.txt', delimiter=',').tolist()
        self.iteration = int(np.loadtxt(path + '/iteration.txt', delimiter=','))
        self.history_deformation = np.load(path + '/history_deformation.npy').tolist()

    def save_csv(self, path: str) -> None:
        """
        Save the history to a CSV file.
        CSV format:
        - Row 1: Column headers (iteration, objective, T0, T1, ..., U0-0, U0-1, ..., UdF0-0-0, UdF0-0-1, ...)
        - Row 2+: Data records
        """
        filepath = path + '/history_record.csv'

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Build column headers
            headers = ['iteration', 'objective']
            
            # Add time consumption column headers
            if self.history_time:
                time_dim = len(self.history_time[0]) if self.history_time[0] else 0
                for i in range(time_dim):
                    headers.append(f'T{i}')

            # Add number of elements and nodes column headers
            headers.append('num_elements')
            headers.append('num_nodes')
            
            # Add deformation history column headers
            if self.history_deformation:
                deform_array = np.array(self.history_deformation[0]) if self.history_deformation[0] is not None else np.array([])
                if deform_array.ndim == 2:  # Matrix
                    rows, cols = deform_array.shape
                    for i in range(rows):
                        for j in range(cols):
                            headers.append(f'U{i}-{j}')
                elif deform_array.ndim == 1:  # Vector
                    for i in range(len(deform_array)):
                        headers.append(f'U0-{i}')
            
            # Row 1: Column headers
            writer.writerow(headers)
            
            # Row 2+: Data records
            max_iterations = self.iteration
            
            for i in range(max_iterations):

                row = [i+1]  # Iteration step
                
                # Objective function value
                if i < len(self.history_objective):
                    row.append(self.history_objective[i])
                else:
                    row.append('')
                
                # Time consumption
                if i < len(self.history_time) and self.history_time[i]:
                    row.extend(self.history_time[i])
                else:
                    # Fill empty values to maintain column consistency
                    time_dim = len(self.history_time[0]) if self.history_time and self.history_time[0] else 0
                    row.extend([''] * time_dim)

                # Number of elements and nodes
                if i < len(self.history_num_elements):
                    row.append(self.history_num_elements[i])
                else:
                    row.append('')

                if i < len(self.history_num_nodes):
                    row.append(self.history_num_nodes[i])
                else:
                    row.append('')
                
                # Deformation history (flattened matrix)
                if i < len(self.history_deformation) and self.history_deformation[i] is not None:
                    deform_flat = np.array(self.history_deformation[i]).flatten()
                    row.extend(deform_flat.tolist())
                else:
                    # Fill empty values to maintain column consistency
                    if self.history_deformation and self.history_deformation[0] is not None:
                        deform_size = np.array(self.history_deformation[0]).size
                        row.extend([''] * deform_size)

                # Format numbers to 4 decimal places in scientific notation, except for iteration
                formatted_row = []
                for idx, val in enumerate(row):
                    if idx == 0:  # Iteration column
                        formatted_row.append(val)
                    elif isinstance(val, float):
                        formatted_row.append(f"{val:.4e}")
                    else:
                        formatted_row.append(val)
                writer.writerow(formatted_row)

    def load_csv(self, path: str) -> None:
        """
        Load the history from a CSV file.
        Reconstructs the original data structure from the flattened CSV format.
        """
        filepath = path + '/history_record.csv'
        
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)

            # Row 1: Column headers
            headers = next(reader)
            
            # Find the indices where different data types start
            objective_idx = headers.index('objective') if 'objective' in headers else 1
            
            # Find time columns
            time_indices = [i for i, h in enumerate(headers) if h.startswith('T')]
            time_start_idx = min(time_indices) if time_indices else None
            time_end_idx = max(time_indices) + 1 if time_indices else None

            # Find element and node columns
            element_indices = [i for i, h in enumerate(headers) if h.startswith('num_elements')]
            element_start_idx = min(element_indices) if element_indices else None
            element_end_idx = max(element_indices) + 1 if element_indices else None

            node_indices = [i for i, h in enumerate(headers) if h.startswith('num_nodes')]
            node_start_idx = min(node_indices) if node_indices else None
            node_end_idx = max(node_indices) + 1 if node_indices else None

            # Find deformation columns (start with U but not UdF)
            deform_indices = [i for i, h in enumerate(headers) if h.startswith('U') and not h.startswith('UdF')]
            deform_start_idx = min(deform_indices) if deform_indices else None
            deform_end_idx = max(deform_indices) + 1 if deform_indices else None
            
            # Determine deformation shape from headers
            deform_shape = None
            if deform_indices:
                u_headers = [headers[i] for i in deform_indices]
                u_indices = [list(map(int, h.replace('U', '').split('-'))) for h in u_headers]
                max_row = max(idx[0] for idx in u_indices) + 1
                max_col = max(idx[1] for idx in u_indices) + 1
                deform_shape = (max_row, max_col)
            
            # Initialize lists
            self.history_objective = []
            self.history_time = []
            self.history_deformation = []
            self.history_compliance = []
            
            # Read data rows
            for row in reader:
                # skip headers and empty rows
                if not row or len(row) == 0 or row[0] == 'iteration':
                    continue

                if not row or len(row) <= objective_idx:  # Skip empty rows
                    continue
                
                # Objective function value
                if row[objective_idx] and row[objective_idx] != '':
                    self.history_objective.append(float(row[objective_idx]))
                else:
                    self.history_objective.append(None)
                
                # Time consumption
                if time_start_idx is not None and time_end_idx is not None:
                    time_data = []
                    for i in range(time_start_idx, time_end_idx):
                        if i < len(row) and row[i] and row[i] != '':
                            time_data.append(float(row[i]))
                        else:
                            time_data.append(0.0)
                    self.history_time.append(time_data)

                if element_start_idx is not None and element_end_idx is not None:
                    if element_start_idx < len(row) and row[element_start_idx] and row[element_start_idx] != '':
                        self.history_num_elements.append(int(float(row[element_start_idx])))
                    else:
                        self.history_num_elements.append(0)
                if node_start_idx is not None and node_end_idx is not None:
                    if node_start_idx < len(row) and row[node_start_idx] and row[node_start_idx] != '':
                        self.history_num_nodes.append(int(float(row[node_start_idx])))
                    else:
                        self.history_num_nodes.append(0)
                
                # Deformation history
                if deform_start_idx is not None and deform_end_idx is not None:
                    deform_data = []
                    for i in range(deform_start_idx, deform_end_idx):
                        if i < len(row) and row[i] and row[i] != '':
                            deform_data.append(float(row[i]))
                        else:
                            deform_data.append(0.0)
                    
                    if deform_data and deform_shape:
                        # Reshape to matrix
                        try:
                            deform_matrix = np.array(deform_data).reshape(deform_shape)
                            self.history_deformation.append(deform_matrix.tolist())
                        except ValueError:
                            # If reshape fails, save as is
                            self.history_deformation.append(deform_data)
                    else:
                        self.history_deformation.append(None)

            # read how many iterations are recorded
            self.iteration = len(self.history_objective)