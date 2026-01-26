import morphopt

if __name__ == "__main__":
    morphopt.start_optimization(path_result='Z:/Results/EXAMPLE_T20260126_190643/',
                                  target_iteration=None,
                                  device='cuda',
                                  restart_per_iteration=10,)