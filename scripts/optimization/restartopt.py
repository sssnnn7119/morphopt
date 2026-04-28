

if __name__ == "__main__":
    import morphopt
    morphopt.start_optimization(path_result='Z:/Results/Twist_Energy_T20260427_201737/',
                                  target_iteration=None,
                                  device='cuda:1',
                                  restart_per_iteration=20,)