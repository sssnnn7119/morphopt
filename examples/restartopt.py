import morphopt

if __name__ == "__main__":
    morphopt.start_optimization(path_result='Z:/Results/EXAMPLE_T20251228_181501/',
                                  target_iteration=None,
                                  device='cuda',
                                  restart_per_iteration=20,)