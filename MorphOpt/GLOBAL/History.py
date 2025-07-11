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
        - Row 1: Current iteration pointer
        - Row 2: Column headers (iteration, objective, time-0, time-1, ..., deformation0-0, deformation0-1, ...)
        - Row 3+: Data records
        """
        filepath = path + '/history_record.csv'

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Row 1: Current iteration pointer
            writer.writerow([self.iteration])
            
            # Build column headers
            headers = ['iteration', 'objective']
            
            # Add time consumption column headers
            if self.history_time:
                time_dim = len(self.history_time[0]) if self.history_time[0] else 0
                for i in range(time_dim):
                    headers.append(f'time-{i}')
            
            # Add deformation history column headers
            if self.history_deformation:
                deform_array = np.array(self.history_deformation[0]) if self.history_deformation[0] is not None else np.array([])
                if deform_array.ndim == 2:  # Matrix
                    rows, cols = deform_array.shape
                    for i in range(rows):
                        for j in range(cols):
                            headers.append(f'deformation{i}-{j}')
                elif deform_array.ndim == 1:  # Vector
                    for i in range(len(deform_array)):
                        headers.append(f'deformation0-{i}')
            
            # Row 2: Column headers
            writer.writerow(headers)
            
            # Row 3+: Data records
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
                
                # Deformation history (flattened matrix)
                if i < len(self.history_deformation) and self.history_deformation[i] is not None:
                    deform_flat = np.array(self.history_deformation[i]).flatten()
                    row.extend(deform_flat.tolist())
                else:
                    # Fill empty values to maintain column consistency
                    if self.history_deformation and self.history_deformation[0] is not None:
                        deform_size = np.array(self.history_deformation[0]).size
                        row.extend([''] * deform_size)
                
                writer.writerow(row)

    def load_csv(self, path: str) -> None:
        """
        Load the history from a CSV file.
        Reconstructs the original data structure from the flattened CSV format.
        """
        filepath = path + '/history_record.csv'
        
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            
            # Row 1: Current iteration pointer
            first_row = next(reader)
            self.iteration = int(first_row[0])
            
            # Row 2: Column headers
            headers = next(reader)
            
            # Find the position of each section in columns
            time_start_idx = None
            time_end_idx = None
            deform_start_idx = None
            deform_cols = 0
            deform_shape = None
            
            for i, header in enumerate(headers):
                if header.startswith('time-') and time_start_idx is None:
                    time_start_idx = i
                elif header.startswith('deformation') and time_start_idx is not None and time_end_idx is None:
                    time_end_idx = i
                    deform_start_idx = i
                    deform_cols += 1
                elif header.startswith('deformation'):
                    if deform_start_idx is None:
                        deform_start_idx = i
                    deform_cols += 1
            
            if time_start_idx is not None and time_end_idx is None:
                time_end_idx = deform_start_idx if deform_start_idx else len(headers)
            
            # Determine deformation matrix shape
            if deform_cols > 0:
                # Infer matrix shape from column headers
                max_row_idx = 0
                max_col_idx = 0
                for header in headers[deform_start_idx:]:
                    if header.startswith('deformation'):
                        parts = header.replace('deformation', '').split('-')
                        if len(parts) == 2:
                            row_idx = int(parts[0])
                            col_idx = int(parts[1])
                            max_row_idx = max(max_row_idx, row_idx)
                            max_col_idx = max(max_col_idx, col_idx)
                deform_shape = (max_row_idx + 1, max_col_idx + 1)
            
            # Initialize lists
            self.history_objective = []
            self.history_time = []
            self.history_deformation = []
            
            # Read data rows
            for row in reader:
                if not row or row[0] == '':  # Skip empty rows
                    continue
                
                # Objective function value
                if len(row) > 1 and row[1] != '':
                    self.history_objective.append(float(row[1]))
                
                # Time consumption
                if time_start_idx is not None and time_end_idx is not None:
                    time_data = []
                    for i in range(time_start_idx, time_end_idx):
                        if i < len(row) and row[i] != '':
                            time_data.append(float(row[i]))
                    if time_data:
                        self.history_time.append(time_data)
                
                # Deformation history
                if deform_start_idx is not None and deform_cols > 0:
                    deform_data = []
                    for i in range(deform_start_idx, deform_start_idx + deform_cols):
                        if i < len(row) and row[i] != '':
                            deform_data.append(float(row[i]))
                    
                    if deform_data and deform_shape:
                        # Reshape to matrix
                        deform_matrix = np.array(deform_data).reshape(deform_shape)
                        self.history_deformation.append(deform_matrix.tolist())
                    elif deform_data:
                        # If shape cannot be determined, save as vector
                        self.history_deformation.append(deform_data)