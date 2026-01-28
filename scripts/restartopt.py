import morphopt

if __name__ == "__main__":
    morphopt.start_optimization(path_result='Z:/Results/FRONT_T20260128_104510/',
                                  target_iteration=None,
                                  device='cuda',
                                  restart_per_iteration=10,)