

if __name__ == "__main__":
    import morphopt
    morphopt.start_optimization(path_result='Z:/Results/EXAMPLE_T20260414_161505/',
                                  target_iteration=None,
                                  device='cuda:1',
                                  restart_per_iteration=20,)