

if __name__ == "__main__":
    import morphopt
    morphopt.start_optimization(path_result='Z:/Results/Twist_Energy_T20260427_104153/',
                                  target_iteration=None,
                                  device='cuda:1',
                                  restart_per_iteration=20,)